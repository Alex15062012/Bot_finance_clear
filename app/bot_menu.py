"""Команды меню бота (кнопка «/» в MAX). Источник — БД / админка."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BotCommandRow
from app.max_api.client import MaxApiClient

logger = logging.getLogger(__name__)

# Fallback, если таблица ещё пустая
DEFAULT_BOT_COMMANDS: list[dict[str, str]] = [
    {"name": "start", "description": "Главное меню"},
    {"name": "materials", "description": "Получить полезные материалы"},
    {"name": "question", "description": "Задать финансовый вопрос"},
    {"name": "help", "description": "Справка по боту"},
]


async def load_commands_for_max(session: AsyncSession) -> list[dict[str, str]]:
    rows = (
        await session.execute(
            select(BotCommandRow)
            .where(BotCommandRow.is_active.is_(True))
            .order_by(BotCommandRow.sort_order.asc(), BotCommandRow.id.asc())
        )
    ).scalars().all()
    if not rows:
        return list(DEFAULT_BOT_COMMANDS)
    return [{"name": r.name, "description": r.description} for r in rows]


async def register_bot_commands(
    api: MaxApiClient,
    session: AsyncSession | None = None,
) -> dict[str, Any] | None:
    """PATCH /me/commands. Если session не передана — берём команды из fallback."""
    try:
        if session is not None:
            commands = await load_commands_for_max(session)
        else:
            commands = list(DEFAULT_BOT_COMMANDS)
        result = await api.set_my_commands(commands)
        logger.info(
            "Bot commands registered: %s",
            ", ".join(c["name"] for c in commands),
        )
        return result
    except Exception:
        logger.exception("Failed to register bot commands")
        return None
