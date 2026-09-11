from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.config import get_settings
from app.db.models import UserState
from app.max_api.client import MaxApiError
from app.max_api.types import extract_chat_id, extract_user
from app.scenarios.base import Scenario, ScenarioContext

logger = logging.getLogger(__name__)


class MaterialsScenario(Scenario):
    """Выдача материалов при bot_started с payload=materials или pending-флагом."""

    code = "materials"

    async def handle(self, ctx: ScenarioContext) -> bool:
        update = ctx.update
        if update.get("update_type") != "bot_started":
            return False

        settings = get_settings()
        payload = (update.get("payload") or "").strip()
        user_data = extract_user(update)
        if not user_data:
            return False

        platform_user_id = int(user_data["user_id"])
        user, created = await ctx.users.get_or_create(
            platform_user_id,
            name=user_data.get("name") or user_data.get("first_name"),
            username=user_data.get("username"),
            source="bot_started",
            dialog_chat_id=extract_chat_id(update),
        )
        if created:
            await ctx.events.track(
                "user_registered",
                user_id=user.id,
                platform_user_id=platform_user_id,
            )

        wants_materials = (
            payload == settings.materials_start_payload
            or user.materials_request_pending
        )
        if not wants_materials:
            return False

        await ctx.events.track(
            "bot_started",
            user_id=user.id,
            platform_user_id=platform_user_id,
            payload={"payload": payload},
        )
        await ctx.users.set_state(user, UserState.BOT_OPENED)

        await ctx.events.track(
            "materials_requested",
            user_id=user.id,
            platform_user_id=platform_user_id,
        )
        user.materials_request_pending = False
        await ctx.users.set_state(user, UserState.MATERIALS_REQUESTED)

        # Автовыдача только при первой выдаче
        if user.materials_sent:
            logger.info(
                "Materials already sent for user %s — skip auto resend",
                platform_user_id,
            )
            if user.state != UserState.QUESTION_RECEIVED.value:
                await ctx.messaging.safe_send_templated(
                    platform_user_id,
                    "question_request",
                    variables={"name": user.name or ""},
                    button_codes=await ctx.content.get_menu_button_codes(),
                )
                await ctx.users.set_state(user, UserState.AWAITING_QUESTION)
            return True

        return await self._deliver_materials(ctx, user, platform_user_id)

    async def deliver_again(self, ctx: ScenarioContext, platform_user_id: int) -> bool:
        """Отдельное действие повторной выдачи (кнопка меню /materials)."""
        user = await ctx.users.get_by_platform_id(platform_user_id)
        if not user:
            return False
        return await self._deliver_materials(
            ctx, user, platform_user_id, force=True, action="materials_resend"
        )

    async def _deliver_materials(
        self,
        ctx: ScenarioContext,
        user,
        platform_user_id: int,
        *,
        force: bool = False,
        action: str = "materials_sent",
    ) -> bool:
        materials = await ctx.content.get_active_materials()
        if not materials:
            logger.warning("No active materials configured")
            return True

        try:
            chat_id = user.dialog_chat_id
            for material in materials:
                await ctx.messaging.send_material(
                    platform_user_id,
                    material,
                    chat_id=chat_id,
                )

            followup = await ctx.messaging.safe_send_templated(
                platform_user_id,
                "question_request",
                variables={"name": user.name or ""},
                button_codes=await ctx.content.get_menu_button_codes(),
                chat_id=chat_id,
            )
            if followup is None:
                logger.error("question_request failed for user %s", platform_user_id)
        except MaxApiError:
            logger.exception("Failed to deliver materials to %s", platform_user_id)
            return True

        if force or not user.materials_sent:
            user.materials_sent = True
            user.materials_sent_at = datetime.now(timezone.utc)

        await ctx.users.set_state(user, UserState.AWAITING_QUESTION)
        await ctx.events.track(
            action,
            user_id=user.id,
            platform_user_id=platform_user_id,
            payload={"count": len(materials), "force": force},
        )
        return True
