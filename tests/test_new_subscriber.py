from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db.base import Base
from app.db.models import UserState
from app.db.models.bot_group import BotGroup
from app.db.models.channel_schedule import ChannelSchedule
from app.db.models.message import MessageTemplate
from app.max_api.client import MaxApiError
from app.scenarios.base import ScenarioContext
from app.scenarios.bot_lifecycle import BotLifecycleScenario
from app.scenarios.menu import MenuScenario
from app.scenarios.new_subscriber import NewSubscriberScenario
from app.scenarios.registry import build_scenarios
from app.seed.content_seed import WELCOME_TEXT, _LEGACY_WELCOME_TEXT, seed_content
from app.services.channel_broadcast import due_slot_keys, send_due_broadcasts
from app.services.content import ContentService
from app.services.events import EventService
from app.services.leads import LeadService
from app.services.users import UserService

MOSCOW = timezone(timedelta(hours=3))


class _Api:
    def __init__(self):
        self.chats: list[int] = []

    async def send_message_to_chat(self, chat_id, text, **kwargs):
        self.chats.append(chat_id)
        self.last_text = text
        self.last_attachments = kwargs.get("attachments")
        return {"ok": True}


class _Messaging:
    def __init__(self):
        self.codes: list[str] = []

    async def safe_send_templated(self, user_id, code, **kwargs):
        self.codes.append(code)
        return {"message": {"body": {"mid": "m1"}}}


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as s:
        yield s
    await engine.dispose()


def _ctx(session, messaging, update) -> ScenarioContext:
    return ScenarioContext(
        session=session,
        api=None,  # type: ignore[arg-type]
        update=update,
        users=UserService(session),
        content=ContentService(session),
        events=EventService(session),
        leads=LeadService(session),
        messaging=messaging,  # type: ignore[arg-type]
    )


def _added(chat_id: int) -> dict:
    return {
        "update_type": "user_added",
        "chat_id": chat_id,
        "user": {"user_id": 42, "name": "Анна", "is_bot": False},
    }


@pytest.mark.asyncio
async def test_new_subscriber_in_tracked_channel_gets_materials_offer(session):
    session.add(
        BotGroup(platform_chat_id=-100, chat_type="channel", status="active", title="Канал")
    )
    await session.flush()
    messaging = _Messaging()
    assert await NewSubscriberScenario().handle(_ctx(session, messaging, _added(-100))) is True
    assert messaging.codes == ["new_subscriber_welcome"]


@pytest.mark.asyncio
async def test_new_subscriber_outside_tracked_chats_is_skipped(session):
    messaging = _Messaging()
    assert await NewSubscriberScenario().handle(_ctx(session, messaging, _added(-5))) is True
    assert messaging.codes == []


def test_default_slots_are_ten_and_sixteen_moscow():
    from app.services.channel_broadcast import default_rules

    rules = default_rules()
    assert due_slot_keys(datetime(2026, 9, 30, 10, 5, tzinfo=MOSCOW), rules)
    assert due_slot_keys(datetime(2026, 9, 30, 16, 0, tzinfo=MOSCOW), rules)
    assert due_slot_keys(datetime(2026, 9, 30, 11, 0, tzinfo=MOSCOW), rules) == []


@pytest.mark.asyncio
async def test_channel_invite_is_sent_once_per_slot(session):
    session.add(
        BotGroup(platform_chat_id=-100, chat_type="channel", status="active", title="Канал")
    )
    session.add(
        BotGroup(platform_chat_id=-200, chat_type="chat", status="active", title="Группа")
    )
    await session.flush()
    api = _Api()
    now = datetime(2026, 9, 30, 10, 1, tzinfo=MOSCOW)
    assert await send_due_broadcasts(session, api, now=now) == 1
    assert api.chats == [-100]
    assert api.last_attachments
    assert await send_due_broadcasts(session, api, now=now) == 0
    assert api.chats == [-100]

    later = datetime(2026, 9, 30, 16, 0, tzinfo=MOSCOW)
    assert await send_due_broadcasts(session, api, now=later) == 1
    assert api.chats == [-100, -100]
    assert "start=question" in str(api.last_attachments)
    assert get_settings().question_deeplink in str(api.last_attachments)


def test_utc_morning_is_moscow_ten():
    from app.services.channel_broadcast import default_rules

    utc = datetime(2026, 9, 30, 7, 0, tzinfo=timezone.utc)
    assert due_slot_keys(utc, default_rules())


@pytest.mark.asyncio
async def test_weekday_and_date_rules_replace_daily_defaults(session):
    session.add(
        BotGroup(platform_chat_id=-100, chat_type="channel", status="active", title="Канал")
    )
    session.add(
        ChannelSchedule(mode="weekday", weekday=0, send_time="10:00", is_active=True)
    )
    session.add(
        ChannelSchedule(mode="date", on_date="2026-10-05", send_time="12:00", is_active=True)
    )
    await session.flush()
    api = _Api()
    wednesday = datetime(2026, 9, 30, 10, 5, tzinfo=MOSCOW)
    assert wednesday.weekday() == 2
    assert await send_due_broadcasts(session, api, now=wednesday) == 0

    monday = datetime(2026, 9, 28, 10, 5, tzinfo=MOSCOW)
    assert monday.weekday() == 0
    assert await send_due_broadcasts(session, api, now=monday) == 1

    once = datetime(2026, 10, 5, 12, 10, tzinfo=MOSCOW)
    assert await send_due_broadcasts(session, api, now=once) == 1
    assert api.chats == [-100, -100]


@pytest.mark.asyncio
async def test_welcome_is_sent_when_subscriber_opens_bot(session):
    users = UserService(session)
    user, _ = await users.get_or_create(42, name="Анна")
    user.subscribed_at = datetime.now(timezone.utc)
    await session.flush()
    messaging = _Messaging()
    update = {
        "update_type": "bot_started",
        "user": {"user_id": 42, "name": "Анна"},
        "chat_id": 50,
    }
    ctx = _ctx(session, messaging, update)
    ctx.users = users
    assert await BotLifecycleScenario().handle(ctx) is False
    assert messaging.codes == ["new_subscriber_welcome"]
    assert user.welcome_sent is True


@pytest.mark.asyncio
async def test_failed_channel_post_is_retried(session):
    session.add(
        BotGroup(platform_chat_id=-100, chat_type="channel", status="active", title="Канал")
    )
    session.add(
        BotGroup(platform_chat_id=-300, chat_type="channel", status="removed", title="Старый")
    )
    await session.flush()

    class _Flaky:
        def __init__(self):
            self.calls = 0

        async def send_message_to_chat(self, chat_id, text, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise MaxApiError("fail", status_code=400, body="no")
            return {"ok": True}

    api = _Flaky()
    now = datetime(2026, 9, 30, 10, 0, tzinfo=MOSCOW)
    assert await send_due_broadcasts(session, api, now=now) == 0
    assert await send_due_broadcasts(session, api, now=now) == 1
    assert api.calls == 2


@pytest.mark.asyncio
async def test_group_member_gets_offer_removed_group_does_not(session):
    session.add(BotGroup(platform_chat_id=-7, chat_type="chat", status="active", title="Группа"))
    session.add(BotGroup(platform_chat_id=-8, chat_type="channel", status="removed", title="Архив"))
    await session.flush()
    messaging = _Messaging()
    scenario = NewSubscriberScenario()
    assert await scenario.handle(_ctx(session, messaging, _added(-7))) is True
    assert messaging.codes == ["new_subscriber_welcome"]
    messaging.codes.clear()
    assert await scenario.handle(_ctx(session, messaging, _added(-8))) is True
    assert messaging.codes == []


@pytest.mark.asyncio
async def test_welcome_does_not_reset_question_state(session):
    session.add(BotGroup(platform_chat_id=-100, chat_type="channel", status="active"))
    await session.flush()
    users = UserService(session)
    user, _ = await users.get_or_create(42, name="Анна")
    await users.set_state(user, UserState.AWAITING_QUESTION)
    messaging = _Messaging()
    ctx = _ctx(session, messaging, _added(-100))
    ctx.users = users
    assert await NewSubscriberScenario().handle(ctx) is True
    assert messaging.codes == ["new_subscriber_welcome"]
    assert user.state == UserState.AWAITING_QUESTION.value


@pytest.mark.asyncio
async def test_user_added_records_channel_and_sends_welcome(session):
    messaging = _Messaging()
    update = {
        "update_type": "user_added",
        "chat_id": -78476736273688,
        "is_channel": True,
        "user": {"user_id": 77, "name": "Олег", "is_bot": False},
    }
    ctx = _ctx(session, messaging, update)
    handled = False
    for scenario in build_scenarios():
        if await scenario.handle(ctx):
            handled = True
            break
    assert handled is True
    assert messaging.codes == ["new_subscriber_welcome"]
    row = (
        await session.execute(select(BotGroup).where(BotGroup.platform_chat_id == -78476736273688))
    ).scalar_one()
    assert row.chat_type == "channel"
    assert row.status == "active"

    api = _Api()
    now = datetime(2026, 9, 30, 16, 10, tzinfo=MOSCOW)
    assert await send_due_broadcasts(session, api, now=now) == 1
    assert api.chats == [-78476736273688]


@pytest.mark.asyncio
async def test_question_deeplink_opens_question_not_menu(session):
    messaging = _Messaging()
    users = UserService(session)
    update = {
        "update_type": "bot_started",
        "payload": "question",
        "chat_id": 50,
        "user": {"user_id": 15, "name": "Ира"},
    }
    ctx = _ctx(session, messaging, update)
    ctx.users = users
    assert await MenuScenario().handle(ctx) is True
    assert messaging.codes == ["question_request"]
    user = await users.get_by_platform_id(15)
    assert user is not None
    assert user.state == UserState.AWAITING_QUESTION.value


@pytest.mark.asyncio
async def test_seed_refreshes_only_untouched_welcome(session):
    session.add(
        MessageTemplate(
            code="new_subscriber_welcome",
            title="Старое",
            text=_LEGACY_WELCOME_TEXT,
            version=1,
        )
    )
    await session.commit()
    await seed_content(session)
    welcome = (
        await session.execute(
            select(MessageTemplate).where(MessageTemplate.code == "new_subscriber_welcome")
        )
    ).scalar_one()
    assert welcome.text == WELCOME_TEXT
    welcome.text = "Текст из админки"
    await session.commit()
    await seed_content(session)
    welcome = (
        await session.execute(
            select(MessageTemplate).where(MessageTemplate.code == "new_subscriber_welcome")
        )
    ).scalar_one()
    assert welcome.text == "Текст из админки"
    codes = (
        await session.execute(
            select(MessageTemplate.code).where(MessageTemplate.code.like("channel_question_%"))
        )
    ).scalars().all()
    assert set(codes) == {
        "channel_question_1",
        "channel_question_2",
        "channel_question_3",
        "channel_question_4",
    }
