from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.db.models import UserState
from app.max_api.types import extract_user
from app.scenarios.base import Scenario, ScenarioContext

logger = logging.getLogger(__name__)


class NewSubscriberScenario(Scenario):
    code = "new_subscriber"

    async def handle(self, ctx: ScenarioContext) -> bool:
        update = ctx.update
        if update.get("update_type") != "user_added":
            return False

        # Только канал (если указан CHANNEL_CHAT_ID — фильтруем)
        from app.config import get_settings

        settings = get_settings()
        chat_id = update.get("chat_id")
        if settings.channel_chat_id and chat_id != settings.channel_chat_id:
            logger.info("Skip user_added for foreign chat_id=%s", chat_id)
            return True

        user_data = extract_user(update)
        if not user_data or user_data.get("is_bot"):
            return True

        platform_user_id = int(user_data["user_id"])
        user, created = await ctx.users.get_or_create(
            platform_user_id,
            name=user_data.get("name") or user_data.get("first_name"),
            username=user_data.get("username"),
            source="channel_subscribe",
        )
        if created:
            await ctx.events.track(
                "user_registered",
                user_id=user.id,
                platform_user_id=platform_user_id,
            )

        await ctx.events.track(
            "new_subscriber",
            user_id=user.id,
            platform_user_id=platform_user_id,
            payload={"chat_id": chat_id},
        )
        user.subscribed_at = user.subscribed_at or datetime.now(timezone.utc)

        if user.welcome_sent:
            logger.info("Welcome already sent for user %s", platform_user_id)
            return True

        name = user.name or "друг"
        result = await ctx.messaging.safe_send_templated(
            platform_user_id,
            "new_subscriber_welcome",
            variables={"name": name, "first_name": name},
            button_codes=["useful_materials"],
        )
        if not result:
            # Состояние не двигаем — возможна повторная отправка
            logger.error("Welcome not sent for user %s — state unchanged", platform_user_id)
            return True

        message_id = None
        if isinstance(result, dict):
            message = result.get("message") or result
            body = message.get("body") if isinstance(message, dict) else None
            if isinstance(body, dict):
                message_id = body.get("mid")
            elif isinstance(message, dict):
                message_id = message.get("id") or message.get("mid")

        user.welcome_sent = True
        user.welcome_sent_at = datetime.now(timezone.utc)
        user.welcome_message_id = str(message_id) if message_id else None
        await ctx.users.set_state(user, UserState.WELCOME_SENT)
        await ctx.events.track(
            "welcome_sent",
            user_id=user.id,
            platform_user_id=platform_user_id,
            payload={"message_id": user.welcome_message_id},
        )
        return True
