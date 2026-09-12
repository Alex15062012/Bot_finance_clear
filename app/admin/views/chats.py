from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import db_session, render, require_admin, set_flash
from app.config import get_settings
from app.db.models import User
from app.max_api.client import MaxApiClient, MaxApiError
from app.services.chat import ChatService
from app.services.content import ContentService
from app.services.messaging import MessagingService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/chats",
    tags=["admin-chats"],
)


@router.get("")
async def list_chats(
    request: Request,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
):
    threads = await ChatService(session).recent_threads()
    return render(
        request,
        "chats/list.html",
        section="chats",
        title="Чаты",
        threads=threads,
    )


@router.get("/{user_id}")
async def chat_detail(
    user_id: int,
    request: Request,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
):
    user = await session.get(User, user_id)
    if not user:
        set_flash(request, "Пользователь не найден", "error")
        return RedirectResponse("/admin/chats", status_code=303)

    chat = ChatService(session)
    messages = await chat.list_for_user(user.id)
    await chat.mark_inbound_read(user.id)
    await session.commit()

    return render(
        request,
        "chats/detail.html",
        section="chats",
        title=f"Чат · {user.name or user.platform_user_id}",
        user=user,
        messages=messages,
    )


@router.post("/{user_id}/send")
async def send_chat_message(
    user_id: int,
    request: Request,
    admin_name: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
    text: str = Form(...),
):
    user = await session.get(User, user_id)
    if not user:
        set_flash(request, "Пользователь не найден", "error")
        return RedirectResponse("/admin/chats", status_code=303)

    body = (text or "").strip()
    if not body:
        set_flash(request, "Введите текст сообщения", "error")
        return RedirectResponse(f"/admin/chats/{user.id}", status_code=303)

    if user.bot_status == "blocked":
        set_flash(
            request,
            "Пользователь остановил бота — сообщение может не дойти",
            "error",
        )

    api = MaxApiClient(get_settings())
    try:
        messaging = MessagingService(session, api, ContentService(session))
        try:
            result = await messaging._send(  # noqa: SLF001
                user.platform_user_id,
                body,
                format=None,
            )
        except MaxApiError as exc:
            logger.warning("Admin chat send failed: %s %s", exc.status_code, exc.body)
            set_flash(request, f"Не удалось отправить в MAX: {exc}", "error")
            return RedirectResponse(f"/admin/chats/{user.id}", status_code=303)
        except Exception:
            logger.exception("Admin chat send failed")
            set_flash(request, "Ошибка отправки сообщения", "error")
            return RedirectResponse(f"/admin/chats/{user.id}", status_code=303)
    finally:
        await api.aclose()

    platform_message_id = None
    if isinstance(result, dict):
        message = result.get("message") or result
        body_obj = message.get("body") if isinstance(message, dict) else None
        if isinstance(body_obj, dict):
            platform_message_id = body_obj.get("mid")
        elif isinstance(message, dict):
            platform_message_id = message.get("id") or message.get("mid")

    await ChatService(session).add_outbound(
        user_id=user.id,
        platform_user_id=user.platform_user_id,
        text=body,
        admin_username=admin_name,
        platform_message_id=str(platform_message_id) if platform_message_id else None,
    )
    await session.commit()
    set_flash(request, "Сообщение отправлено пользователю в бот")
    return RedirectResponse(f"/admin/chats/{user.id}", status_code=303)
