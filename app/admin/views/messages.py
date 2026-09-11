from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import db_session, render, require_admin, set_flash
from app.db.models import MessageTemplate

router = APIRouter(
    prefix='/messages',
    tags=['admin-messages'],
)


@router.get("")
async def list_messages(
    request: Request,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
):
    rows = (
        await session.execute(
            select(MessageTemplate).order_by(MessageTemplate.code.asc())
        )
    ).scalars().all()
    return render(
        request,
        "messages/list.html",
        section="messages",
        title="Тексты сообщений",
        messages=rows,
    )


@router.get("/{message_id}")
async def edit_message_page(
    message_id: int,
    request: Request,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
):
    row = await session.get(MessageTemplate, message_id)
    if not row:
        set_flash(request, "Сообщение не найдено", "error")
        return RedirectResponse("/admin/messages", status_code=303)
    return render(
        request,
        "messages/edit.html",
        section="messages",
        title=f"Текст: {row.code}",
        message=row,
    )


@router.post("/{message_id}")
async def save_message(
    message_id: int,
    request: Request,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
    title: str = Form(...),
    text: str = Form(...),
    is_active: str | None = Form(None),
):
    row = await session.get(MessageTemplate, message_id)
    if not row:
        set_flash(request, "Сообщение не найдено", "error")
        return RedirectResponse("/admin/messages", status_code=303)

    row.title = title.strip()
    row.text = text
    row.is_active = is_active == "on"
    row.version = int(row.version or 1) + 1
    await session.commit()
    set_flash(request, f"Сохранено: {row.code} (v{row.version})")
    return RedirectResponse(f"/admin/messages/{row.id}", status_code=303)
