"""Регистрация webhook-подписки в MAX."""

from __future__ import annotations

import asyncio
import logging

from app.config import get_settings
from app.logging_setup import setup_logging
from app.max_api.client import MaxApiClient

logger = logging.getLogger(__name__)

UPDATE_TYPES = [
    "message_created",
    "bot_started",
    "bot_stopped",
    "dialog_removed",
    "user_added",
    "user_removed",
    "bot_added",
    "message_callback",
]


async def run() -> None:
    settings = get_settings()
    setup_logging(settings)

    if not settings.webhook_url:
        raise SystemExit("Укажите WEBHOOK_URL в .env")
    if not settings.max_bot_token or settings.max_bot_token == "replace_me":
        raise SystemExit("Укажите MAX_BOT_TOKEN в .env")

    api = MaxApiClient(settings)
    try:
        result = await api.subscribe(
            settings.webhook_url,
            update_types=UPDATE_TYPES,
            secret=settings.webhook_secret or None,
        )
        logger.info("Webhook subscribed: %s", result)
    finally:
        await api.aclose()


if __name__ == "__main__":
    asyncio.run(run())
