import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import Button, MessageTemplate
from app.seed.content_seed import seed_content


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
async def test_second_seed_does_not_overwrite_admin_edits(session: AsyncSession):
    await seed_content(session)

    button = (
        await session.execute(select(Button).where(Button.code == "menu_question"))
    ).scalar_one()
    button.title = "Свой вопрос"
    button.is_active = False

    message = (
        await session.execute(
            select(MessageTemplate).where(MessageTemplate.code == "bot_main_menu")
        )
    ).scalar_one()
    message.text = "Текст из админки"
    await session.commit()

    await seed_content(session)

    button = (
        await session.execute(select(Button).where(Button.code == "menu_question"))
    ).scalar_one()
    message = (
        await session.execute(
            select(MessageTemplate).where(MessageTemplate.code == "bot_main_menu")
        )
    ).scalar_one()
    assert button.title == "Свой вопрос"
    assert button.is_active is False
    assert message.text == "Текст из админки"
