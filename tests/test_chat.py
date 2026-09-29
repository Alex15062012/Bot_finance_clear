import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import Lead, User, UserState
from app.db.models.chat_message import ChatDirection, ChatMessage
from app.scenarios.base import ScenarioContext
from app.scenarios.chat_inbound import ChatInboundScenario
from app.services.chat import ChatService
from app.services.content import ContentService
from app.services.events import EventService
from app.services.leads import LeadService
from app.services.users import UserService


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
async def test_chat_inbound_outbound_and_unread(session: AsyncSession):
    users = UserService(session)
    user, _ = await users.get_or_create(501, name="Chat User")
    chat = ChatService(session)

    await chat.add_inbound(
        user_id=user.id,
        platform_user_id=501,
        text="Привет от пользователя",
        platform_message_id="m1",
    )
    # duplicate platform id ignored
    assert (
        await chat.add_inbound(
            user_id=user.id,
            platform_user_id=501,
            text="Привет от пользователя",
            platform_message_id="m1",
        )
        is None
    )

    await chat.add_outbound(
        user_id=user.id,
        platform_user_id=501,
        text="Ответ админа",
        admin_username="admin",
    )

    messages = await chat.list_for_user(user.id)
    assert len(messages) == 2
    assert messages[0].direction == ChatDirection.INBOUND.value
    assert messages[1].direction == ChatDirection.OUTBOUND.value

    threads = await chat.recent_threads()
    assert len(threads) == 1
    assert threads[0]["unread"] == 1

    await chat.mark_inbound_read(user.id)
    threads = await chat.recent_threads()
    assert threads[0]["unread"] == 0


@pytest.mark.asyncio
async def test_chat_opens_after_question_or_admin(session: AsyncSession):
    users = UserService(session)
    user, _ = await users.get_or_create(502, name="Анна")
    chat = ChatService(session)
    assert await chat.can_user_write(user.id) is False

    session.add(
        Lead(user_id=user.id, question="Куда уходит прибыль?", source="question_request")
    )
    await session.flush()
    assert await chat.can_user_write(user.id) is True


@pytest.mark.asyncio
async def test_chat_opens_after_admin_message(session: AsyncSession):
    users = UserService(session)
    user, _ = await users.get_or_create(503, name="Борис")
    chat = ChatService(session)
    await chat.add_outbound(
        user_id=user.id,
        platform_user_id=503,
        text="Здравствуйте",
        admin_username="admin",
    )
    assert await chat.can_user_write(user.id) is True


class _Messaging:
    def __init__(self):
        self.codes: list[str] = []

    async def safe_send_templated(self, user_id, code, **kwargs):
        self.codes.append(code)
        return {"ok": True}


@pytest.mark.asyncio
async def test_inbound_before_chat_is_not_stored(session: AsyncSession):
    users = UserService(session)
    await users.get_or_create(504, name="Нина")
    messaging = _Messaging()
    ctx = ScenarioContext(
        session=session,
        api=None,  # type: ignore[arg-type]
        update={
            "update_type": "message_created",
            "message": {
                "sender": {"user_id": 504, "name": "Нина"},
                "body": {"text": "Хочу написать в чат", "mid": "x1"},
            },
        },
        users=users,
        content=ContentService(session),
        events=EventService(session),
        leads=LeadService(session),
        messaging=messaging,  # type: ignore[arg-type]
    )
    assert await ChatInboundScenario().handle(ctx) is True
    assert messaging.codes == ["chat_locked"]
    stored = (await session.execute(select(ChatMessage))).scalar_one_or_none()
    assert stored is None
