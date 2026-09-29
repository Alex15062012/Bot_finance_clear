from __future__ import annotations

import logging

from app.db.models import UserState
from app.max_api.types import (
    extract_chat_id,
    extract_message_id,
    extract_message_text,
    extract_user,
)
from app.scenarios.base import Scenario, ScenarioContext

logger = logging.getLogger(__name__)


class QuestionScenario(Scenario):
    code = "question"

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

        # Команды и подписи кнопок меню не являются текстом вопроса.
        if text.strip().startswith("/"):
            return False
        from app.scenarios.menu import resolve_menu_text

        if await resolve_menu_text(ctx.content, text):
            return False

        platform_user_id = int(user_data["user_id"])
        user = await ctx.users.get_by_platform_id(platform_user_id)
        if not user:
            user, _ = await ctx.users.get_or_create(
                platform_user_id,
                name=user_data.get("name") or user_data.get("first_name"),
                username=user_data.get("username"),
                source="direct_message",
                dialog_chat_id=extract_chat_id(update),
            )
        else:
            chat_id = extract_chat_id(update)
            if chat_id and user.dialog_chat_id != chat_id:
                user.dialog_chat_id = chat_id
                await ctx.session.flush()

        if user.state != UserState.AWAITING_QUESTION.value:
            return False

        await save_question(ctx, user, platform_user_id, text.strip())
        return True


async def save_question(ctx: ScenarioContext, user, platform_user_id: int, text: str) -> None:
    """Сохраняет текст вопроса в обращения админки и подтверждает пользователю."""
    message_id = extract_message_id(ctx.update)
    lead, created = await ctx.leads.create_if_new(
        user_id=user.id,
        question=text.strip(),
        source="question_request",
        platform_message_id=message_id,
    )
    if not created:
        logger.info("Duplicate lead for message %s", message_id)
        return

    await ctx.events.track(
        "question_received",
        user_id=user.id,
        platform_user_id=platform_user_id,
        payload={"lead_id": lead.id},
    )
    await ctx.events.track(
        "lead_created",
        user_id=user.id,
        platform_user_id=platform_user_id,
        payload={"lead_id": lead.id, "status": lead.status},
    )
    await ctx.users.set_state(user, UserState.QUESTION_RECEIVED)
    logger.info("Lead #%s saved from user %s", lead.id, platform_user_id)

    await ctx.messaging.safe_send_templated(
        platform_user_id,
        "question_received_ack",
        variables={"name": user.name or ""},
        button_codes=await ctx.content.get_menu_button_codes(),
    )
