from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy import text
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


async def _ensure_column(conn, table: str, column: str, ddl: str) -> None:
    """Лёгкая миграция: добавить колонку, если её ещё нет."""
    if _settings.database_url.startswith("sqlite"):
        cols = (await conn.execute(text(f"PRAGMA table_info({table})"))).fetchall()
        names = {row[1] for row in cols}
        if column not in names:
            await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))
        return

    # PostgreSQL
    exists = (
        await conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :table AND column_name = :column"
            ),
            {"table": table, "column": column},
        )
    ).scalar_one_or_none()
    if exists is None:
        await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))


async def init_db() -> None:
    from app.db import Base  # noqa: F401 — register models
    import app.db.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _ensure_column(conn, "users", "dialog_chat_id", "dialog_chat_id BIGINT")
        await _ensure_column(
            conn,
            "users",
            "bot_status",
            "bot_status VARCHAR(32) DEFAULT 'active'",
        )
        await _ensure_column(conn, "users", "blocked_at", "blocked_at TIMESTAMP")
        await _ensure_column(
            conn,
            "users",
            "is_admin",
            "is_admin BOOLEAN DEFAULT FALSE",
        )
