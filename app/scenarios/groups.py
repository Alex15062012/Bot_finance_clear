"""Учёт групп и каналов, куда добавлен бот."""

from __future__ import annotations

import logging

from app.scenarios.base import Scenario, ScenarioContext
from app.services.bot_groups import (
    remember_bot_added,
    remember_bot_removed,
    remember_seen_chat,
)

logger = logging.getLogger(__name__)


class GroupsScenario(Scenario):
    code = "groups"

    async def handle(self, ctx: ScenarioContext) -> bool:
        update_type = str(ctx.update.get("update_type") or "")
        if update_type == "bot_added":
            row = await remember_bot_added(ctx.session, ctx.update, ctx.api)
            if row:
                logger.info(
                    "Bot added to %s chat_id=%s by user_id=%s",
                    row.chat_type,
                    row.platform_chat_id,
                    row.added_by_user_id,
                )
            return True
        if update_type == "bot_removed":
            row = await remember_bot_removed(ctx.session, ctx.update, ctx.api)
            if row:
                logger.info("Bot removed from chat_id=%s", row.platform_chat_id)
            return True
        await remember_seen_chat(ctx.session, ctx.update, ctx.api)
        return False
