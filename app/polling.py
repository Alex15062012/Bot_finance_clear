"""Long polling для локальной разработки (не для production)."""

from __future__ import annotations

import asyncio
import logging

import httpx

from app.bot_menu import register_bot_commands
from app.config import get_settings
from app.db.session import SessionLocal, init_db
from app.handlers.update_router import UpdateRouter
from app.logging_setup import setup_logging
from app.max_api.client import MaxApiClient
from app.seed.content_seed import seed_content

logger = logging.getLogger(__name__)

UPDATE_TYPES = [
    "message_created",
    "bot_started",
    "user_added",
    "user_removed",
    "bot_added",
    "message_callback",
]

POLL_TIMEOUT_SEC = 25


async def run() -> None:
    settings = get_settings()
    setup_logging(settings)

    if not settings.max_bot_token or settings.max_bot_token == "replace_me":
        raise SystemExit("Укажите MAX_BOT_TOKEN в .env")

    await init_db()
    async with SessionLocal() as session:
        await seed_content(session)

    api = MaxApiClient(settings)
    async with SessionLocal() as session:
        await register_bot_commands(api, session)
    router = UpdateRouter(api)
    marker: int | None = None

    logger.info("Long polling started (timeout=%ss)", POLL_TIMEOUT_SEC)
    try:
        while True:
            try:
                data = await api.get_updates(
                    marker=marker,
                    timeout=POLL_TIMEOUT_SEC,
                    types=UPDATE_TYPES,
                )
            except httpx.TimeoutException:
                # Пустой long-poll: сервер/прокси молчал дольше ожидаемого — просто цикл
                logger.debug("get_updates timeout, continue")
                continue
            except Exception:
                logger.exception("get_updates failed, retry in 3s")
                await asyncio.sleep(3)
                continue

            if not data:
                continue

            marker = data.get("marker", marker)
            updates = data.get("updates") or []
            if updates:
                logger.info("Received %s update(s)", len(updates))
            for update in updates:
                async with SessionLocal() as session:
                    await router.handle(session, update)
    finally:
        await api.aclose()


if __name__ == "__main__":
    asyncio.run(run())
