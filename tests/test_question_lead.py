import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import Lead, UserState
from app.scenarios.base import ScenarioContext
from app.scenarios.question import QuestionScenario
from app.services.content import ContentService
from app.services.events import EventService
from app.services.leads import LeadService
from app.services.users import UserService


class _Messaging:
    async def safe_send_templated(self, *args, **kwargs):
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
