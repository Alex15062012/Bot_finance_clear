import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import Button, Lead, UserState
from app.scenarios.base import ScenarioContext
from app.scenarios.menu import MenuScenario
from app.scenarios.question import QuestionScenario
from app.services.content import ContentService
from app.services.events import EventService
from app.services.leads import LeadService
from app.services.users import UserService


class _Api:
    async def answer_callback(self, callback_id: str, **kwargs):
        return {"ok": True}


class _Messaging:
    def __init__(self):
        self.sent: list[tuple] = []

    async def safe_send_templated(self, *args, **kwargs):
        self.sent.append((args, kwargs))
        return {"ok": True}

    async def get_menu_button_codes(self):
        return []


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_waiting_user_text_becomes_lead(session: AsyncSession):
    users = UserService(session)
    user, _ = await users.get_or_create(42, name="Анна")
    await users.set_state(user, UserState.AWAITING_QUESTION)

    ctx = ScenarioContext(
        session=session,
        api=None,  # type: ignore[arg-type]
        update={
            "update_type": "message_created",
            "message": {
                "sender": {"user_id": 42, "name": "Анна"},
                "body": {"text": "Как распределить бюджет?", "mid": "mid-1"},
            },
        },
        users=users,
        content=ContentService(session),
        events=EventService(session),
        leads=LeadService(session),
        messaging=_Messaging(),  # type: ignore[arg-type]
    )

    assert await QuestionScenario().handle(ctx) is True
    lead = (await session.execute(select(Lead))).scalar_one()
    assert lead.question == "Как распределить бюджет?"
    assert lead.user_id == user.id
    assert lead.status == "new"
    assert user.state == UserState.QUESTION_RECEIVED.value


@pytest.mark.asyncio
async def test_menu_button_title_is_not_a_lead(session: AsyncSession):
    session.add(
        Button(
            code="menu_home",
            title="☰ Меню",
            action_type="message",
            payload="/start",
            scenario="menu",
            is_active=True,
            sort_order=1,
        )
    )
    await session.flush()
    users = UserService(session)
    user, _ = await users.get_or_create(7, name="Евгений")
    await users.set_state(user, UserState.AWAITING_QUESTION)
    ctx = ScenarioContext(
        session=session,
        api=None,  # type: ignore[arg-type]
        update={
            "update_type": "message_created",
            "message": {
                "sender": {"user_id": 7, "name": "Евгений"},
                "body": {"text": "☰ Меню", "mid": "mid-menu"},
            },
        },
        users=users,
        content=ContentService(session),
        events=EventService(session),
        leads=LeadService(session),
        messaging=_Messaging(),  # type: ignore[arg-type]
    )
    assert await QuestionScenario().handle(ctx) is False
    assert (await session.execute(select(Lead))).scalar_one_or_none() is None
    assert user.state == UserState.AWAITING_QUESTION.value


@pytest.mark.asyncio
async def test_question_button_uses_clicker_not_bot_author(session: AsyncSession):
    """Клавиатура висит на сообщении бота, но состояние нужно человеку, который нажал кнопку."""
    users = UserService(session)
    human, _ = await users.get_or_create(5600001, name="Евгений")
    messaging = _Messaging()
    click = {
        "update_type": "message_callback",
        "chat_id": 383694387,
        "callback": {
            "callback_id": "cb-1",
            "payload": "menu:question",
            "user": {"user_id": 5600001, "name": "Евгений", "is_bot": False},
        },
        "message": {
            "sender": {"user_id": 378258738, "name": "Помощник", "is_bot": True},
            "recipient": {"chat_id": 383694387, "chat_type": "dialog"},
            "body": {"text": "Меню", "mid": "bot-mid"},
        },
    }
    ctx = ScenarioContext(
        session=session,
        api=_Api(),  # type: ignore[arg-type]
        update=click,
        users=users,
        content=ContentService(session),
        events=EventService(session),
        leads=LeadService(session),
        messaging=messaging,  # type: ignore[arg-type]
    )
    assert await MenuScenario().handle(ctx) is True
    assert human.state == UserState.AWAITING_QUESTION.value
    assert any(call[0][1] == "question_request" for call in messaging.sent)

    reply = {
        "update_type": "message_created",
        "chat_id": 383694387,
        "message": {
            "sender": {"user_id": 5600001, "name": "Евгений", "is_bot": False},
            "recipient": {"chat_id": 383694387, "chat_type": "dialog"},
            "body": {"text": "Я вам пишу чего же боле", "mid": "human-mid"},
        },
    }
    ctx.update = reply
    assert await QuestionScenario().handle(ctx) is True
    lead = (await session.execute(select(Lead))).scalar_one()
    assert lead.question == "Я вам пишу чего же боле"
    assert lead.user_id == human.id
    assert any(call[0][1] == "question_received_ack" for call in messaging.sent)
