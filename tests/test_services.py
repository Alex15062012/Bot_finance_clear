import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import LeadStatus, User, UserState
from app.services.idempotency import IdempotencyService
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
async def test_user_unique(session: AsyncSession):
    users = UserService(session)
    u1, created1 = await users.get_or_create(100, name="A", source="t")
    u2, created2 = await users.get_or_create(100, name="A")
    assert created1 is True
    assert created2 is False
    assert u1.id == u2.id


@pytest.mark.asyncio
async def test_user_block_and_reactivate(session: AsyncSession):
    from app.db.models.user import BotUsageStatus

    users = UserService(session)
    user, _ = await users.get_or_create(200, name="B", source="bot_started")
    assert user.bot_status == BotUsageStatus.ACTIVE.value

    await users.mark_blocked(user)
    assert user.bot_status == BotUsageStatus.BLOCKED.value
    assert user.blocked_at is not None

    user2, created = await users.get_or_create(200, name="B", mark_active=True)
    assert created is False
    assert user2.bot_status == BotUsageStatus.ACTIVE.value
    assert user2.blocked_at is None


@pytest.mark.asyncio
async def test_idempotency(session: AsyncSession):
    svc = IdempotencyService(session)
    assert await svc.try_claim("k1", "user_added") is True
    assert await svc.try_claim("k1", "user_added") is False


@pytest.mark.asyncio
async def test_lead_dedupe(session: AsyncSession):
    session.add(User(platform_user_id=1, state=UserState.AWAITING_QUESTION.value))
    await session.flush()
    user = (await session.execute(select(User))).scalar_one()

    leads = LeadService(session)
    lead1, c1 = await leads.create_if_new(
        user_id=user.id, question="Q", platform_message_id="m1"
    )
    lead2, c2 = await leads.create_if_new(
        user_id=user.id, question="Q", platform_message_id="m1"
    )
    assert c1 is True
    assert c2 is False
    assert lead1.id == lead2.id
    assert lead1.status == LeadStatus.NEW.value
