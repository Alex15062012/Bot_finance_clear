import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import Button, Material, MaterialType, UserState
from app.scenarios.base import ScenarioContext
from app.scenarios.materials import MaterialsScenario
from app.services.content import ContentService
from app.services.events import EventService
from app.services.leads import LeadService
from app.services.users import UserService


class _Api:
    async def answer_callback(self, callback_id: str, **kwargs):
        return {"ok": True}


class _Messaging:
    def __init__(self):
        self.templates: list[str] = []
        self.materials: list[int] = []
        self.texts: list[str] = []

    async def safe_send_templated(self, user_id, code, **kwargs):
        self.templates.append(code)
        return {"ok": True}

    async def send_material(self, user_id, material, **kwargs):
        self.materials.append(material.id)
        return {"ok": True}

    async def _send(self, user_id, text, **kwargs):
        self.texts.append(text)
        return {"ok": True}

    async def _build_button(self, button):
        return {"text": button.title, "payload": button.payload}


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
        api=_Api(),  # type: ignore[arg-type]
        update=update,
        users=UserService(session),
        content=ContentService(session),
        events=EventService(session),
        leads=LeadService(session),
        messaging=messaging,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_materials_list_does_not_ask_question(session: AsyncSession):
    session.add(
        Material(
            title="Где прибыль",
            content_type=MaterialType.TEXT.value,
            content="Текст",
            sort_order=1,
            is_active=True,
        )
    )
    await session.flush()
    users = UserService(session)
    user, _ = await users.get_or_create(1, name="Анна")
    messaging = _Messaging()
    scenario = MaterialsScenario()
    await scenario._offer_materials(  # noqa: SLF001
        _ctx(session, messaging, {}),
        user,
        1,
    )
    assert messaging.templates == []
    assert messaging.materials == []
    assert messaging.texts
    assert user.state == UserState.MATERIALS_SENT.value


@pytest.mark.asyncio
async def test_question_after_one_material_opened(session: AsyncSession):
    material = Material(
        title="Где прибыль",
        content_type=MaterialType.TEXT.value,
        content="Текст",
        sort_order=1,
        is_active=True,
    )
    session.add(material)
    await session.flush()
    users = UserService(session)
    user, _ = await users.get_or_create(2, name="Борис")
    await users.set_state(user, UserState.MATERIALS_SENT)
    messaging = _Messaging()
    scenario = MaterialsScenario()
    update = {
        "update_type": "message_callback",
        "callback": {
            "callback_id": "cb",
            "payload": f"material:{material.id}",
            "user": {"user_id": 2, "name": "Борис"},
        },
        "message": {
            "sender": {"user_id": 999, "name": "Бот", "is_bot": True},
            "recipient": {"chat_id": 50, "chat_type": "dialog"},
        },
    }
    assert await scenario.handle(_ctx(session, messaging, update)) is True
    assert messaging.materials == [material.id]
    assert messaging.templates == ["question_request"]
    assert user.state == UserState.AWAITING_QUESTION.value

    messaging.templates.clear()
    messaging.materials.clear()
    messaging.texts.clear()
    assert await scenario.handle(_ctx(session, messaging, update)) is True
    assert messaging.materials == [material.id]
    assert messaging.templates == []
    assert user.state == UserState.AWAITING_QUESTION.value


@pytest.mark.asyncio
async def test_materials_list_hides_get_materials_button(session: AsyncSession):
    session.add(
        Button(
            code="menu_materials",
            title="Получить материалы",
            action_type="callback",
            payload="menu:materials",
            is_active=True,
            sort_order=1,
        )
    )
    session.add(
        Button(
            code="menu_question",
            title="Задать вопрос",
            action_type="callback",
            payload="menu:question",
            is_active=True,
            sort_order=2,
        )
    )
    await session.flush()
    messaging = _Messaging()
    rows = await MaterialsScenario()._menu_rows(_ctx(session, messaging, {}))  # noqa: SLF001
    titles = [row[0]["text"] for row in rows]
    assert titles == ["Задать вопрос"]


@pytest.mark.asyncio
async def test_materials_list_is_sent_again(session: AsyncSession):
    session.add(
        Material(
            title="Где прибыль",
            content_type=MaterialType.TEXT.value,
            content="Текст",
            sort_order=1,
            is_active=True,
        )
    )
    await session.flush()
    users = UserService(session)
    user, _ = await users.get_or_create(3, name="Нина")
    messaging = _Messaging()
    scenario = MaterialsScenario()
    ctx = _ctx(session, messaging, {})
    await scenario._offer_materials(ctx, user, 3)  # noqa: SLF001
    messaging.texts.clear()
    await scenario._offer_materials(ctx, user, 3)  # noqa: SLF001
    assert len(messaging.texts) == 1
    assert "уже ранее получили" not in messaging.texts[0]
