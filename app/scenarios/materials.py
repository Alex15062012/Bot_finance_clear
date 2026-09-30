from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.config import get_settings
from sqlalchemy import select

from app.db.models import Material, UserState
from app.db.models.user_material_delivery import UserMaterialDelivery
from app.max_api.client import MaxApiError, callback_button, inline_keyboard
from app.max_api.types import extract_chat_id, extract_user, sent_message_mid
from app.scenarios.base import Scenario, ScenarioContext
from app.services.templates import render_template

logger = logging.getLogger(__name__)


class MaterialsScenario(Scenario):
    """Выдача материалов при bot_started с payload=materials или pending-флагом."""

    code = "materials"

    async def handle(self, ctx: ScenarioContext) -> bool:
        update = ctx.update
        if update.get("update_type") == "message_callback":
            return await self._on_material_open(ctx)
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
        await ctx.events.track(
            "materials_requested",
            user_id=user.id,
            platform_user_id=platform_user_id,
        )
        user.materials_request_pending = False
        if user.state not in {
            UserState.AWAITING_QUESTION.value,
            UserState.QUESTION_RECEIVED.value,
        }:
            await ctx.users.set_state(user, UserState.MATERIALS_REQUESTED)

        return await self._offer_materials(ctx, user, platform_user_id)

    async def deliver_again(self, ctx: ScenarioContext, platform_user_id: int) -> bool:
        """Отдельное действие повторной выдачи (кнопка меню /materials)."""
        user = await ctx.users.get_by_platform_id(platform_user_id)
        if not user:
            return False
        return await self._offer_materials(
            ctx, user, platform_user_id, action="materials_resend"
        )

    async def _offer_materials(
        self,
        ctx: ScenarioContext,
        user,
        platform_user_id: int,
        *,
        action: str = "materials_sent",
    ) -> bool:
        """Список материалов. При каждом запросе список отправляется заново."""
        materials = await ctx.content.get_active_materials()
        if not materials:
            logger.warning("No active materials configured")
            return True

        template = await ctx.content.get_message("materials_choose")
        if template:
            text = render_template(template.text, {"name": user.name or ""})
        else:
            text = "Выберите материал. Финансовый вопрос появится после того, как вы откроете один из них."

        rows: list[list[dict]] = []
        for material in materials:
            title = (material.title or f"Материал {material.id}").strip()
            rows.append([callback_button(title[:120], f"material:{material.id}")])
        rows.extend(await self._menu_rows(ctx))

        try:
            sent = await ctx.messaging._send(  # noqa: SLF001
                platform_user_id,
                text,
                attachments=[inline_keyboard(rows)],
                chat_id=user.dialog_chat_id,
            )
        except MaxApiError:
            logger.exception("Failed to offer materials to %s", platform_user_id)
            return True

        user.materials_sent = True
        user.materials_sent_at = datetime.now(timezone.utc)
        user.materials_list_message_id = sent_message_mid(sent)
        if user.state not in {
            UserState.AWAITING_QUESTION.value,
            UserState.QUESTION_RECEIVED.value,
        }:
            await ctx.users.set_state(user, UserState.MATERIALS_SENT)
        await ctx.events.track(
            action,
            user_id=user.id,
            platform_user_id=platform_user_id,
            payload={"count": len(materials)},
        )
        return True

    async def _on_material_open(self, ctx: ScenarioContext) -> bool:
        callback = ctx.update.get("callback") or {}
        payload = str(callback.get("payload") or "")
        if not payload.startswith("material:"):
            return False

        callback_id = callback.get("callback_id")
        if callback_id:
            try:
                await ctx.api.answer_callback(str(callback_id))
            except Exception as exc:
                logger.warning(
                    "answer_callback failed: %s body=%s",
                    exc,
                    getattr(exc, "body", None),
                )

        raw_id = payload.split(":", 1)[1]
        try:
            material_id = int(raw_id)
        except ValueError:
            return True

        material = await ctx.session.get(Material, material_id)
        user_data = extract_user(ctx.update)
        if not user_data or not material or not material.is_active:
            return True

        platform_user_id = int(user_data["user_id"])
        user, _ = await ctx.users.get_or_create(
            platform_user_id,
            name=user_data.get("name") or user_data.get("first_name"),
            username=user_data.get("username"),
            source="material_open",
            dialog_chat_id=extract_chat_id(ctx.update),
        )
        try:
            sent = await ctx.messaging.send_material(
                platform_user_id,
                material,
                chat_id=user.dialog_chat_id,
            )
        except MaxApiError:
            logger.exception(
                "Failed to send material %s to %s", material_id, platform_user_id
            )
            return True

        previous = await self._delivery(ctx, user.id, material.id)
        mid = sent_message_mid(sent)
        if previous is None:
            ctx.session.add(
                UserMaterialDelivery(
                    user_id=user.id,
                    material_id=material.id,
                    message_mid=mid,
                )
            )
        else:
            previous.message_mid = mid
            previous.sent_at = datetime.now(timezone.utc)
        await ctx.session.flush()
        await ctx.events.track(
            "material_opened",
            user_id=user.id,
            platform_user_id=platform_user_id,
            payload={"material_id": material.id},
        )
        if user.state in {
            UserState.AWAITING_QUESTION.value,
            UserState.QUESTION_RECEIVED.value,
        }:
            return True

        followup = await ctx.messaging.safe_send_templated(
            platform_user_id,
            "question_request",
            variables={"name": user.name or ""},
            button_codes=await ctx.content.get_menu_button_codes(),
            chat_id=user.dialog_chat_id,
        )
        if followup is None:
            logger.error("question_request failed for user %s", platform_user_id)
            return True
        await ctx.users.set_state(user, UserState.AWAITING_QUESTION)
        return True

    async def _delivery(
        self, ctx: ScenarioContext, user_id: int, material_id: int
    ) -> UserMaterialDelivery | None:
        return (
            await ctx.session.execute(
                select(UserMaterialDelivery).where(
                    UserMaterialDelivery.user_id == user_id,
                    UserMaterialDelivery.material_id == material_id,
                )
            )
        ).scalar_one_or_none()

    async def _menu_rows(self, ctx: ScenarioContext) -> list[list[dict]]:
        rows: list[list[dict]] = []
        for code in await ctx.content.get_menu_button_codes():
            button = await ctx.content.get_button(code)
            if not button:
                continue
            built = await ctx.messaging._build_button(button)  # noqa: SLF001
            if built:
                rows.append([built])
        return rows
