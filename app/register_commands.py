"""Регистрация меню команд бота в MAX (PATCH /me/commands) из БД."""

from __future__ import annotations

import asyncio
import logging

from app.bot_menu import register_bot_commands
from app.config import get_settings
from app.db.session import SessionLocal, init_db
from app.logging_setup import setup_logging
from app.max_api.client import MaxApiClient
from app.seed.content_seed import seed_content

logger = logging.getLogger(__name__)


async def run() -> None:
    settings = get_settings()
    setup_logging(settings)
    if not settings.max_bot_token or settings.max_bot_token == "replace_me":
        raise SystemExit("Укажите MAX_BOT_TOKEN в .env")

    await init_db()
    async with SessionLocal() as session:
        await seed_content(session)

    api = MaxApiClient(settings)
    try:
        async with SessionLocal() as session:
            result = await register_bot_commands(api, session)
        if result is None:
            raise SystemExit(1)
        logger.info("Done: %s", result)
    finally:
        await api.aclose()


if __name__ == "__main__":
    asyncio.run(run())
