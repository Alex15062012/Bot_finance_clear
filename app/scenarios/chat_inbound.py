"""Сохранение входящих сообщений пользователя для переписки в админке."""

from __future__ import annotations

import logging

from app.max_api.types import (
    extract_chat_id,
    extract_message_id,
    extract_message_text,
    extract_user,
)
from app.scenarios.base import Scenario, ScenarioContext
from app.services.chat import ChatService

logger = logging.getLogger(__name__)


class ChatInboundScenario(Scenario):
    """Пишет в chat_messages любые текстовые сообщения (не команды)."""

    code = "chat_inbound"

    async def handle(self, ctx: ScenarioContext) -> bool:
        update = ctx.update
        if update.get("update_type") != "message_created":
            return False

        user_data = extract_user(update)
        if not user_data or user_data.get("is_bot"):
            return False

        text = extract_message_text(update)
        if not text or not text.strip():
            return False
        if text.strip().startswith("/"):
            return False

        platform_user_id = int(user_data["user_id"])
        user, _ = await ctx.users.get_or_create(
            platform_user_id,
            name=user_data.get("name") or user_data.get("first_name"),
            username=user_data.get("username"),
            source="chat",
            dialog_chat_id=extract_chat_id(update),
        )

        chat = ChatService(ctx.session)
        row = await chat.add_inbound(
            user_id=user.id,
            platform_user_id=platform_user_id,
            text=text.strip(),
            platform_message_id=extract_message_id(update),
        )
        if row:
            await ctx.events.track(
                "chat_inbound",
                user_id=user.id,
                platform_user_id=platform_user_id,
                payload={"chat_message_id": row.id},
            )
            logger.info("Inbound chat from %s stored id=%s", platform_user_id, row.id)

        # False — QuestionScenario и другие могут обработать дальше
        return False
