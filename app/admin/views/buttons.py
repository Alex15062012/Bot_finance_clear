from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import db_session, render, require_admin, set_flash
from app.db.models import Button

router = APIRouter(
    prefix="/buttons",
    tags=["admin-buttons"],
)


@router.get("")
async def list_buttons(
    request: Request,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
):
    rows = (
        await session.execute(
            select(Button).order_by(Button.sort_order.asc(), Button.id.asc())
        )
    ).scalars().all()
    return render(
        request,
        "buttons/list.html",
        section="buttons",
        title="Кнопки меню",
        buttons=rows,
    )


@router.get("/{button_id}")
async def edit_button_page(
    button_id: int,
    request: Request,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
):
    row = await session.get(Button, button_id)
    if not row:
        set_flash(request, "Кнопка не найдена", "error")
        return RedirectResponse("/admin/buttons", status_code=303)
    return render(
        request,
        "buttons/edit.html",
        section="buttons",
        title=f"Кнопка: {row.code}",
        button=row,
    )


@router.post("/{button_id}")
async def save_button(
    button_id: int,
    request: Request,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
    title: str = Form(...),
    action_type: str = Form(...),
    url: str = Form(""),
    payload: str = Form(""),
    scenario: str = Form(""),
    sort_order: int = Form(0),
    is_active: str | None = Form(None),
):
    row = await session.get(Button, button_id)
    if not row:
        set_flash(request, "Кнопка не найдена", "error")
        return RedirectResponse("/admin/buttons", status_code=303)

    row.title = title.strip()
    row.action_type = action_type.strip()
    row.url = url.strip() or None
    row.payload = payload.strip() or None
    row.scenario = scenario.strip() or None
    row.sort_order = sort_order
    row.is_active = is_active == "on"
    await session.commit()
    set_flash(request, f"Кнопка {row.code} сохранена")
    return RedirectResponse(f"/admin/buttons/{row.id}", status_code=303)
