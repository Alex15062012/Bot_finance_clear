import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.services.bot_groups import (
    list_groups,
    remember_bot_added,
    remember_bot_removed,
    remember_seen_chat,
    sync_groups_from_api,
)


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
async def test_bot_added_stores_channel_and_admin(session: AsyncSession):
    row = await remember_bot_added(
        session,
        {
            "update_type": "bot_added",
            "timestamp": 1_700_000_000_000,
            "chat_id": -100123,
            "is_channel": True,
            "user": {"user_id": 5600001, "name": "Евгений", "username": "evg"},
        },
    )
    assert row is not None
    assert row.platform_chat_id == -100123
    assert row.chat_type == "channel"
    assert row.type_label == "Канал"
    assert row.added_by_user_id == 5600001
    assert row.added_by_name == "Евгений"
    assert row.status == "active"
    assert len(await list_groups(session)) == 1


@pytest.mark.asyncio
async def test_bot_removed_keeps_chat_id(session: AsyncSession):
    await remember_bot_added(
        session,
        {
            "update_type": "bot_added",
            "chat_id": 42,
            "is_channel": False,
            "user": {"user_id": 7, "name": "Админ"},
        },
    )
    row = await remember_bot_removed(
        session,
        {"update_type": "bot_removed", "chat_id": 42, "is_channel": False},
    )
    assert row is not None
    assert row.platform_chat_id == 42
    assert row.chat_type == "chat"
    assert row.status == "removed"
    assert row.removed_at is not None


@pytest.mark.asyncio
async def test_private_dialog_is_not_listed(session: AsyncSession):
    class _Api:
        async def get_chat(self, chat_id: int) -> dict:
            return {"chat_id": chat_id, "type": "dialog", "status": "active"}

    row = await remember_bot_added(
        session,
        {
            "update_type": "bot_added",
            "chat_id": 99,
            "is_channel": False,
            "user": {"user_id": 1, "name": "А"},
        },
        api=_Api(),
    )
    assert row is None
    assert await list_groups(session) == []


@pytest.mark.asyncio
async def test_channel_message_is_remembered_once(session: AsyncSession):
    update = {
        "update_type": "message_created",
        "timestamp": 1_700_000_100,
        "message": {
            "recipient": {"chat_id": 555, "chat_type": "channel"},
            "sender": {"user_id": 1, "name": "Кто-то"},
        },
    }
    first = await remember_seen_chat(session, update)
    second = await remember_seen_chat(session, update)
    assert first is not None
    assert second is not None
    assert first.id == second.id
    assert first.chat_type == "channel"
    assert first.added_by_user_id is None
    rows = await list_groups(session)
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_dialog_message_is_ignored(session: AsyncSession):
    await remember_seen_chat(
        session,
        {
            "update_type": "message_created",
            "message": {"recipient": {"chat_id": 1, "chat_type": "dialog"}},
        },
    )
    assert await list_groups(session) == []


@pytest.mark.asyncio
async def test_sync_finds_channel_and_skips_dialog(session: AsyncSession):
    class _Api:
        async def get_updates(self, *, marker=None, timeout=0, limit=100, types=None):
            if marker is None:
                return {"updates": [], "marker": 10_000}
            if marker == 10_000 - 5_000:
                return {
                    "updates": [
                        {
                            "update_type": "bot_added",
                            "timestamp": 1_700_000_000_000,
                            "chat_id": 77,
                            "is_channel": True,
                            "user": {"user_id": 5, "name": "Анна"},
                        },
                        {
                            "update_type": "bot_added",
                            "chat_id": 88,
                            "is_channel": False,
                            "user": {"user_id": 6, "name": "Борис"},
                        },
                    ],
                    "marker": 10_000,
                }
            return {"updates": [], "marker": 10_000}

        async def get_chat(self, chat_id: int) -> dict:
            if chat_id == 88:
                return {
                    "chat_id": chat_id,
                    "type": "dialog",
                    "status": "active",
                    "messages_count": 10,
                }
            return {
                "chat_id": chat_id,
                "type": "channel",
                "status": "active",
                "title": "Канал тест",
                "link": "https://max.ru/test",
                "participants_count": 4,
                "messages_count": 99,
            }

    count = await sync_groups_from_api(session, _Api())
    rows = await list_groups(session)
    assert count == 1
    assert rows[0].platform_chat_id == 77
    assert rows[0].title == "Канал тест"
    assert rows[0].link == "https://max.ru/test"
    assert rows[0].participants_count == 4
    assert rows[0].added_by_name == "Анна"
    assert "messages_count" not in rows[0].__table__.columns
