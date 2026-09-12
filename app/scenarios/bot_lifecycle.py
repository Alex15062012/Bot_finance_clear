"""Регистрация пользователя при открытии бота и учёт остановки/бана."""

from __future__ import annotations

import logging

from app.db.models import UserState
from app.max_api.types import extract_chat_id, extract_user
from app.scenarios.base import Scenario, ScenarioContext

logger = logging.getLogger(__name__)

# MAX: bot_stopped — остановил/удалил бота; dialog_removed — удалил диалог
_BLOCK_EVENTS = frozenset({"bot_stopped", "dialog_removed"})


class BotLifecycleScenario(Scenario):
    """
    Гарантирует запись в users при любом открытии бота (bot_started),
    даже без дальнейших действий, и отмечает «забанил бота» при остановке.
    """

    code = "bot_lifecycle"

    async def handle(self, ctx: ScenarioContext) -> bool:
        update_type = str(ctx.update.get("update_type") or "")

        if update_type == "bot_started":
            return await self._on_started(ctx)

        if update_type in _BLOCK_EVENTS:
            return await self._on_blocked(ctx, update_type)

        return False

    async def _on_started(self, ctx: ScenarioContext) -> bool:
        user_data = extract_user(ctx.update)
        if not user_data or user_data.get("is_bot"):
            return False

        platform_user_id = int(user_data["user_id"])
        user, created = await ctx.users.get_or_create(
            platform_user_id,
            name=user_data.get("name") or user_data.get("first_name"),
            username=user_data.get("username"),
            source="bot_started",
            dialog_chat_id=extract_chat_id(ctx.update),
            mark_active=True,
        )
        if created:
            await ctx.events.track(
                "user_registered",
                user_id=user.id,
                platform_user_id=platform_user_id,
                payload={"via": "bot_opened"},
            )

        if user.state in {
            UserState.NEW_SUBSCRIBER.value,
            UserState.WELCOME_SENT.value,
        }:
            await ctx.users.set_state(user, UserState.BOT_OPENED)

        await ctx.events.track(
            "bot_opened",
            user_id=user.id,
            platform_user_id=platform_user_id,
            payload={"payload": ctx.update.get("payload")},
        )
        # False — дальше Materials / Menu обработают сценарий
        return False

    async def _on_blocked(self, ctx: ScenarioContext, update_type: str) -> bool:
        user_data = extract_user(ctx.update)
        if not user_data or user_data.get("is_bot"):
            return True

        platform_user_id = int(user_data["user_id"])
        user, created = await ctx.users.get_or_create(
            platform_user_id,
            name=user_data.get("name") or user_data.get("first_name"),
            username=user_data.get("username"),
            source=update_type,
            dialog_chat_id=extract_chat_id(ctx.update),
            mark_active=False,
        )
        if created:
            await ctx.events.track(
                "user_registered",
                user_id=user.id,
                platform_user_id=platform_user_id,
                payload={"via": update_type},
            )

        await ctx.users.mark_blocked(user)
        await ctx.events.track(
            "bot_blocked",
            user_id=user.id,
            platform_user_id=platform_user_id,
            payload={"update_type": update_type},
        )
        logger.info(
            "User %s marked blocked (%s)",
            platform_user_id,
            update_type,
        )
        return True
