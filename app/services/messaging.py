from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Material, MaterialType
from app.max_api.client import (
    MaxApiClient,
    MaxApiError,
    callback_button,
    inline_keyboard,
    link_button,
    message_button,
)
from app.services.content import ContentService
from app.services.templates import render_template
from app.services.users import UserService

logger = logging.getLogger(__name__)


class MessagingService:
    def __init__(
        self,
        session: AsyncSession,
        api: MaxApiClient,
        content: ContentService,
    ):
        self.session = session
        self.api = api
        self.content = content
        self.users = UserService(session)

    async def _send(
        self,
        platform_user_id: int,
        text: str,
        *,
        attachments: list[dict[str, Any]] | None = None,
        format: str | None = "markdown",
        chat_id: int | None = None,
    ) -> dict[str, Any]:
        """
        В личку MAX надёжнее слать по dialog chat_id.
        user_id часто даёт 403 chat.denied / Invalid chatId: 0.
        """
        resolved_chat_id = chat_id
        if resolved_chat_id is None:
            user = await self.users.get_by_platform_id(platform_user_id)
            if user and user.dialog_chat_id:
                resolved_chat_id = int(user.dialog_chat_id)

        if resolved_chat_id:
            try:
                return await self.api.send_message_to_chat(
                    resolved_chat_id,
                    text,
                    attachments=attachments,
                    format=format,
                )
            except MaxApiError as exc:
                logger.warning(
                    "send by chat_id=%s failed (%s), fallback to user_id=%s: %s",
                    resolved_chat_id,
                    exc.status_code,
                    platform_user_id,
                    exc.body,
                )

        return await self.api.send_message_to_user(
            platform_user_id,
            text,
            attachments=attachments,
            format=format,
        )

    async def send_templated(
        self,
        user_id: int,
        message_code: str,
        *,
        variables: dict[str, Any] | None = None,
        button_codes: list[str] | None = None,
        chat_id: int | None = None,
    ) -> dict[str, Any]:
        template = await self.content.get_message(message_code)
        if not template:
            raise ValueError(f"Message template not found: {message_code}")

        text = render_template(template.text, variables)
        attachments: list[dict[str, Any]] = []

        if button_codes:
            rows: list[list[dict[str, Any]]] = []
            for code in button_codes:
                button = await self.content.get_button(code)
                if not button:
                    logger.warning("Button not found: %s", code)
                    continue
                built = await self._build_button(button)
                if built:
                    rows.append([built])
            if rows:
                attachments.append(inline_keyboard(rows))

        return await self._send(
            user_id,
            text,
            attachments=attachments or None,
            chat_id=chat_id,
        )

    async def _build_button(self, button) -> dict[str, Any] | None:
        action = button.action_type
        if action in {"open_bot", "link"}:
            url = button.url
            if not url and action == "open_bot":
                url = await self.content.get_setting("useful_materials_deeplink")
            if url:
                return link_button(button.title, url)
            return None
        if action == "callback":
            payload = button.payload or button.code
            return callback_button(button.title, payload)
        if action == "message":
            return message_button(button.title, button.payload or button.title)
        logger.warning("Unsupported button action_type=%s code=%s", action, button.code)
        return None

    async def send_material(
        self,
        user_id: int,
        material: Material,
        *,
        chat_id: int | None = None,
    ) -> dict[str, Any]:
        content_type = material.content_type
        text_parts: list[str] = []
        if material.title:
            text_parts.append(f"**{material.title}**")
        if material.description:
            text_parts.append(material.description)
        if content_type == MaterialType.TEXT.value and material.content:
            text_parts.append(material.content)
        if content_type == MaterialType.LINK.value and material.url:
            text_parts.append(material.url)
        if material.content and content_type not in {
            MaterialType.TEXT.value,
            MaterialType.LINK.value,
        }:
            text_parts.append(material.content)
        if material.url and content_type not in {MaterialType.LINK.value}:
            text_parts.append(material.url)

        text = "\n\n".join(part for part in text_parts if part) or material.title
        attachments: list[dict[str, Any]] | None = None

        if material.file_token:
            attachment_type = {
                MaterialType.IMAGE.value: "image",
                MaterialType.VIDEO.value: "video",
                MaterialType.DOCUMENT.value: "file",
            }.get(content_type, "file")
            attachments = [
                {"type": attachment_type, "payload": {"token": material.file_token}}
            ]
        elif content_type == MaterialType.IMAGE.value and material.url:
            attachments = [{"type": "image", "payload": {"url": material.url}}]

        try:
            return await self._send(
                user_id,
                text,
                attachments=attachments,
                chat_id=chat_id,
            )
        except MaxApiError:
            # Markdown иногда ломает отправку — повтор без format
            logger.warning("Material send with markdown failed, retry plain text")
            return await self._send(
                user_id,
                text.replace("**", ""),
                attachments=attachments,
                format=None,
                chat_id=chat_id,
            )

    async def safe_send_templated(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        try:
            return await self.send_templated(*args, **kwargs)
        except MaxApiError:
            logger.exception("Failed to send templated message")
            return None
        except Exception:
            logger.exception("Unexpected error while sending message")
            return None
