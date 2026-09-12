from __future__ import annotations

import logging
import re

from app.admin_access import admin_public_url, is_bot_admin
from app.db.models import UserState
from app.max_api.client import inline_keyboard, link_button
from app.max_api.types import extract_chat_id, extract_message_text, extract_user
from app.scenarios.base import Scenario, ScenarioContext
from app.scenarios.materials import MaterialsScenario

logger = logging.getLogger(__name__)

_COMMAND_RE = re.compile(r"^/([a-zA-Z0-9_]+)(?:@\w+)?(?:\s+(.*))?$", re.DOTALL)


def parse_command(text: str) -> tuple[str, str] | None:
    match = _COMMAND_RE.match(text.strip())
    if not match:
        return None
    return match.group(1).lower(), (match.group(2) or "").strip()


class MenuScenario(Scenario):
    """Команды меню и inline-кнопки в личном чате с ботом."""

    code = "menu"

    async def handle(self, ctx: ScenarioContext) -> bool:
        update = ctx.update
        update_type = update.get("update_type")

        if update_type == "bot_started":
            return await self._on_bot_started(ctx)

        if update_type == "message_callback":
            return await self._on_callback(ctx)

        if update_type == "message_created":
            return await self._on_message(ctx)

        return False

    async def _menu_buttons(self, ctx: ScenarioContext) -> list[str]:
        return await ctx.content.get_menu_button_codes()

    async def _on_bot_started(self, ctx: ScenarioContext) -> bool:
        """Если пришли не за материалами — показываем меню."""
        from app.config import get_settings

        settings = get_settings()
        payload = (update_payload := (ctx.update.get("payload") or "").strip())
        if payload == settings.materials_start_payload:
            return False  # MaterialsScenario

        user_data = extract_user(ctx.update)
        if not user_data:
            return True

        platform_user_id = int(user_data["user_id"])
        user, created = await ctx.users.get_or_create(
            platform_user_id,
            name=user_data.get("name") or user_data.get("first_name"),
            username=user_data.get("username"),
            source="bot_started",
            dialog_chat_id=extract_chat_id(ctx.update),
        )
        if created:
            await ctx.events.track(
                "user_registered",
                user_id=user.id,
                platform_user_id=platform_user_id,
            )
        await ctx.events.track(
            "bot_started",
            user_id=user.id,
            platform_user_id=platform_user_id,
            payload={"payload": update_payload},
        )
        await self._send_main_menu(ctx, user, platform_user_id)
        return True

    async def _on_message(self, ctx: ScenarioContext) -> bool:
        text = extract_message_text(ctx.update)
        if not text:
            return False

        parsed = parse_command(text)
        if not parsed:
            normalized = text.strip().lower()
            # Ярлыки по названиям кнопок из БД
            buttons = []
            for code in await self._menu_buttons(ctx):
                btn = await ctx.content.get_button(code)
                if btn:
                    buttons.append(btn)
            aliases = {
                "меню": "menu",
                "помощь": "help",
                "получить материалы": "materials",
                "получить полезные материалы": "materials",
                "задать вопрос": "question",
                "админ": "admin",
                "админка": "admin",
            }
            for btn in buttons:
                aliases[btn.title.strip().lower()] = (btn.payload or "").removeprefix(
                    "menu:"
                ) or btn.code.removeprefix("menu_")
            cmd = aliases.get(normalized)
            if not cmd:
                return False
            args = ""
        else:
            cmd, args = parsed

        user_data = extract_user(ctx.update)
        if not user_data or user_data.get("is_bot"):
            return False

        platform_user_id = int(user_data["user_id"])
        user, _ = await ctx.users.get_or_create(
            platform_user_id,
            name=user_data.get("name") or user_data.get("first_name"),
            username=user_data.get("username"),
            source="menu_command",
            dialog_chat_id=extract_chat_id(ctx.update),
        )

        await ctx.events.track(
            "menu_command",
            user_id=user.id,
            platform_user_id=platform_user_id,
            payload={"command": cmd, "args": args},
        )

        if cmd in {"start", "menu"}:
            await self._send_main_menu(ctx, user, platform_user_id)
            return True
        if cmd == "help":
            await ctx.messaging.safe_send_templated(
                platform_user_id,
                "bot_help",
                variables={"name": user.name or ""},
                button_codes=await self._menu_buttons(ctx),
            )
            return True
        if cmd == "materials":
            await self._give_materials(ctx, platform_user_id)
            return True
        if cmd == "question":
            await self._ask_question(ctx, user, platform_user_id)
            return True
        if cmd == "admin":
            await self._send_admin_link(ctx, user, platform_user_id)
            return True

        return False

    async def _on_callback(self, ctx: ScenarioContext) -> bool:
        callback = ctx.update.get("callback") or {}
        payload = str(callback.get("payload") or "")
        if not payload.startswith("menu:"):
            return False

        callback_id = callback.get("callback_id")
        if callback_id:
            try:
                await ctx.api.answer_callback(str(callback_id))
            except Exception as exc:
                # Не блокируем сценарий: callback мог устареть
                logger.warning(
                    "answer_callback failed: %s body=%s",
                    exc,
                    getattr(exc, "body", None),
                )

        action = payload.split(":", 1)[1]
        user_data = extract_user(ctx.update)
        if not user_data:
            return True

        platform_user_id = int(user_data["user_id"])
        user, _ = await ctx.users.get_or_create(
            platform_user_id,
            name=user_data.get("name") or user_data.get("first_name"),
            username=user_data.get("username"),
            source="menu_callback",
            dialog_chat_id=extract_chat_id(ctx.update),
        )
        await ctx.events.track(
            "menu_button_clicked",
            user_id=user.id,
            platform_user_id=platform_user_id,
            payload={"action": action},
        )

        if action == "materials":
            await self._give_materials(ctx, platform_user_id)
        elif action == "question":
            await self._ask_question(ctx, user, platform_user_id)
        elif action == "help":
            await ctx.messaging.safe_send_templated(
                platform_user_id,
                "bot_help",
                variables={"name": user.name or ""},
                button_codes=await self._menu_buttons(ctx),
            )
        elif action == "menu":
            await self._send_main_menu(ctx, user, platform_user_id)
        else:
            return False
        return True

    async def _send_main_menu(self, ctx: ScenarioContext, user, platform_user_id: int) -> None:
        await ctx.messaging.safe_send_templated(
            platform_user_id,
            "bot_main_menu",
            variables={"name": user.name or "друг"},
            button_codes=await self._menu_buttons(ctx),
        )

    async def _ask_question(self, ctx: ScenarioContext, user, platform_user_id: int) -> None:
        await ctx.users.set_state(user, UserState.AWAITING_QUESTION)
        await ctx.messaging.safe_send_templated(
            platform_user_id,
            "question_request",
            variables={"name": user.name or ""},
            button_codes=await self._menu_buttons(ctx),
        )

    async def _send_admin_link(self, ctx: ScenarioContext, user, platform_user_id: int) -> None:
        if not is_bot_admin(platform_user_id, user=user):
            logger.warning(
                "admin denied for platform_user_id=%s",
                platform_user_id,
            )
            text = (
                "Нет доступа к веб-админке.\n\n"
                f"Ваш MAX user_id: `{platform_user_id}`\n\n"
                "Администратор может назначить вас в разделе «Пользователи» веб-админки "
                "или добавить ID в `ADMIN_PLATFORM_USER_IDS` в `.env`."
            )
            try:
                await ctx.messaging._send(platform_user_id, text)  # noqa: SLF001
            except Exception:
                logger.exception("Failed to send admin deny hint")
            return

        url = admin_public_url()
        if "localhost" in url or "127.0.0.1" in url:
            text = (
                "Админка доступна только по публичному URL сервера.\n\n"
                f"Сейчас в настройках: {url}\n\n"
                "Укажите `ADMIN_PUBLIC_URL=http://IP_ИЛИ_ДОМЕН:8000/admin` в `.env` "
                "и перезапустите контейнер/сервис `web`."
            )
            try:
                await ctx.messaging._send(platform_user_id, text)  # noqa: SLF001
            except Exception:
                logger.exception("Failed to send admin localhost hint")
            return

        text = (
            "Здравствуйте! 👋\n\n"
            "Ваша панель управления ботом — здесь можно менять тексты, меню и смотреть обращения:\n"
            f"{url}"
        )
        attachments = [inline_keyboard([[link_button("Открыть админку", url)]])]
        try:
            await ctx.messaging._send(  # noqa: SLF001
                platform_user_id,
                text,
                attachments=attachments,
            )
        except Exception:
            logger.exception("Failed to send admin link")

    async def _give_materials(self, ctx: ScenarioContext, platform_user_id: int) -> None:
        materials = MaterialsScenario()
        user = await ctx.users.get_by_platform_id(platform_user_id)
        if user and user.materials_sent:
            await materials.deliver_again(ctx, platform_user_id)
            return

        if user:
            user.materials_request_pending = False
            await materials._deliver_materials(ctx, user, platform_user_id)  # noqa: SLF001
        else:
            await materials.deliver_again(ctx, platform_user_id)
