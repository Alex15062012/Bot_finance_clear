import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import User, UserState
from app.db.models.chat_message import ChatDirection
from app.services.chat import ChatService
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
