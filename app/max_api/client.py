from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)

DEFAULT_CA_BUNDLE = Path(__file__).resolve().parents[2] / "certs" / "ca-bundle.pem"


def resolve_verify(settings: Settings) -> bool | str:
    """
    SSL verify для MAX API.
    По умолчанию — бандл certifi + сертификаты Минцифры (certs/ca-bundle.pem).
    """
    if not settings.max_ssl_verify:
        logger.warning("MAX_SSL_VERIFY=false — проверка TLS отключена")
        return False

    if settings.max_ca_bundle:
        path = Path(settings.max_ca_bundle)
        if not path.is_file():
            raise FileNotFoundError(f"MAX_CA_BUNDLE not found: {path}")
        return str(path)

    if DEFAULT_CA_BUNDLE.is_file():
        return str(DEFAULT_CA_BUNDLE)

    logger.warning(
        "certs/ca-bundle.pem не найден — используется системный CA store. "
        "При SSL ошибке выполните: python -m app.tools.build_ca_bundle"
    )
    return True


class MaxApiError(Exception):
    def __init__(self, message: str, status_code: int | None = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class MaxApiClient:
    """Тонкий адаптер к MAX Bot API. Бизнес-логика сюда не попадает."""

    def __init__(self, settings: Settings):
        self._settings = settings
        verify = resolve_verify(settings)
        # read > long-poll timeout, иначе httpx обрывает пустой /updates как ReadTimeout
        self._client = httpx.AsyncClient(
            base_url=settings.max_api_base_url.rstrip("/"),
            headers={"Authorization": settings.max_bot_token},
            timeout=httpx.Timeout(connect=10.0, read=90.0, write=30.0, pool=10.0),
            verify=verify,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        timeout: httpx.Timeout | float | None = None,
    ) -> Any:
        response = await self._client.request(
            method,
            path,
            params=params,
            json=json,
            timeout=timeout,
        )
        if response.status_code >= 400:
            raise MaxApiError(
                f"MAX API {method} {path} failed: {response.status_code}",
                status_code=response.status_code,
                body=response.text,
            )
        if not response.content:
            return None
        return response.json()

    async def get_me(self) -> dict[str, Any]:
        return await self._request("GET", "/me")

    async def set_my_commands(self, commands: list[dict[str, str]]) -> dict[str, Any]:
        """PATCH /me/commands — меню команд бота (до 32 шт.)."""
        return await self._request(
            "PATCH",
            "/me/commands",
            json={"commands": commands},
        )

    async def answer_callback(
        self,
        callback_id: str,
        *,
        notification: str | None = None,
    ) -> dict[str, Any]:
        # Пустое тело {} допустимо; без body MAX часто отвечает 400.
        body: dict[str, Any] = {}
        if notification:
            body["notification"] = notification
        return await self._request(
            "POST",
            "/answers",
            params={"callback_id": callback_id},
            json=body,
        )

    async def send_message_to_user(
        self,
        user_id: int,
        text: str,
        *,
        attachments: list[dict[str, Any]] | None = None,
        format: str | None = "markdown",
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"text": text}
        if format:
            body["format"] = format
        if attachments:
            body["attachments"] = attachments
        return await self._request(
            "POST",
            "/messages",
            params={"user_id": user_id},
            json=body,
        )

    async def send_message_to_chat(
        self,
        chat_id: int,
        text: str,
        *,
        attachments: list[dict[str, Any]] | None = None,
        format: str | None = "markdown",
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"text": text}
        if format:
            body["format"] = format
        if attachments:
            body["attachments"] = attachments
        return await self._request(
            "POST",
            "/messages",
            params={"chat_id": chat_id},
            json=body,
        )

    async def get_updates(
        self,
        *,
        marker: int | None = None,
        timeout: int = 30,
        limit: int = 100,
        types: list[str] | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"timeout": timeout, "limit": limit}
        if marker is not None:
            params["marker"] = marker
        if types:
            params["types"] = ",".join(types)
        # HTTP read-timeout должен быть строго больше server-side long-poll timeout
        http_timeout = httpx.Timeout(
            connect=10.0,
            read=float(timeout) + 20.0,
            write=30.0,
            pool=10.0,
        )
        return await self._request(
            "GET",
            "/updates",
            params=params,
            timeout=http_timeout,
        )

    async def subscribe(
        self,
        url: str,
        *,
        update_types: list[str] | None = None,
        secret: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"url": url}
        if update_types:
            body["update_types"] = update_types
        if secret:
            body["secret"] = secret
        return await self._request("POST", "/subscriptions", json=body)

    async def get_upload_url(self, upload_type: str) -> dict[str, Any]:
        return await self._request("POST", "/uploads", params={"type": upload_type})


def inline_keyboard(rows: list[list[dict[str, Any]]]) -> dict[str, Any]:
    return {"type": "inline_keyboard", "payload": {"buttons": rows}}


def link_button(text: str, url: str) -> dict[str, Any]:
    return {"type": "link", "text": text, "url": url}


def callback_button(text: str, payload: str) -> dict[str, Any]:
    return {"type": "callback", "text": text, "payload": payload}


def message_button(text: str, payload: str | None = None) -> dict[str, Any]:
    """Кнопка, которая отправляет боту заранее заданный текст."""
    btn: dict[str, Any] = {"type": "message", "text": text}
    if payload is not None:
        btn["payload"] = payload
    return btn
