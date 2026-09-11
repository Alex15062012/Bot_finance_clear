from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

_settings = get_settings()

if _settings.database_url.startswith("sqlite"):
    Path("data").mkdir(parents=True, exist_ok=True)

engine = create_async_engine(
    _settings.database_url,
    echo=False,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    from sqlalchemy import text

    from app.db import Base  # noqa: F401 — register models
    import app.db.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Лёгкая миграция SQLite: dialog_chat_id для POST /messages
        if _settings.database_url.startswith("sqlite"):
            cols = (
                await conn.execute(text("PRAGMA table_info(users)"))
            ).fetchall()
            names = {row[1] for row in cols}
            if "dialog_chat_id" not in names:
                await conn.execute(
                    text("ALTER TABLE users ADD COLUMN dialog_chat_id BIGINT")
                )
