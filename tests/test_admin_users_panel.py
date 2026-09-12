import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models.admin_user import AdminUser
from app.services.admin_users import (
    deactivate_admin_for_bot_user,
    suggest_admin_login,
    upsert_admin_for_bot_user,
    validate_admin_credentials,
)
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


def test_validate_admin_credentials():
    assert validate_admin_credentials("ab", "123456") is not None
    assert validate_admin_credentials("admin1", "123") is not None
    assert validate_admin_credentials("admin1", "123456") is None


@pytest.mark.asyncio
async def test_upsert_admin_for_bot_user(session: AsyncSession):
    users = UserService(session)
    user, _ = await users.get_or_create(777, name="A", username="max_user")
    assert suggest_admin_login(user) == "max_user"

    account = await upsert_admin_for_bot_user(
        session, user, username="max_user", password="secret1"
    )
    assert account.username == "max_user"
    assert account.bot_user_id == user.id
    assert account.is_active is True

    again = await upsert_admin_for_bot_user(
        session, user, username="max_user", password="secret2"
    )
    assert again.id == account.id

    await deactivate_admin_for_bot_user(session, user.id)
    await session.refresh(account)
    assert account.is_active is False
