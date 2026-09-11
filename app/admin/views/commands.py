from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import db_session, render, require_admin, set_flash
from app.bot_menu import register_bot_commands
from app.db.models import BotCommandRow

router = APIRouter(
    prefix="/commands",
    tags=["admin-commands"],
)


@router.get("")
async def list_commands(
    request: Request,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
):
    rows = (
        await session.execute(
            select(BotCommandRow).order_by(
                BotCommandRow.sort_order.asc(), BotCommandRow.id.asc()
            )
        )
    ).scalars().all()
    return render(
        request,
        "commands/list.html",
        section="commands",
        title="Меню у поля ввода",
        commands=rows,
    )


@router.get("/{command_id}")
async def edit_command_page(
    command_id: int,
    request: Request,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
):
    row = await session.get(BotCommandRow, command_id)
    if not row:
        set_flash(request, "Команда не найдена", "error")
        return RedirectResponse("/admin/commands", status_code=303)
    return render(
        request,
        "commands/edit.html",
        section="commands",
        title=f"Команда /{row.name}",
        command=row,
    )


@router.post("/{command_id}")
async def save_command(
    command_id: int,
    request: Request,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
    name: str = Form(...),
    description: str = Form(...),
    sort_order: int = Form(0),
    is_active: str | None = Form(None),
    sync: str | None = Form(None),
):
    row = await session.get(BotCommandRow, command_id)
    if not row:
        set_flash(request, "Команда не найдена", "error")
        return RedirectResponse("/admin/commands", status_code=303)

    clean_name = name.strip().lstrip("/").lower()
    if not clean_name or len(clean_name) > 64:
        set_flash(request, "Некорректное имя команды", "error")
        return RedirectResponse(f"/admin/commands/{command_id}", status_code=303)

    row.name = clean_name
    row.description = description.strip()[:128]
    row.sort_order = sort_order
    row.is_active = is_active == "on"
    await session.commit()

    if sync == "1":
        api = request.app.state.api
        result = await register_bot_commands(api, session)
        if result is None:
            set_flash(request, "Сохранено, но синхронизация с MAX не удалась", "error")
        else:
            set_flash(request, "Сохранено и синхронизировано с меню MAX")
    else:
        set_flash(request, "Сохранено. Нажмите «Синхронизировать с MAX», чтобы обновить кнопку /")

    return RedirectResponse(f"/admin/commands/{row.id}", status_code=303)


@router.post("/sync")
async def sync_commands(
    request: Request,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
):
    api = request.app.state.api
    result = await register_bot_commands(api, session)
    if result is None:
        set_flash(request, "Не удалось синхронизировать меню с MAX", "error")
    else:
        set_flash(request, "Меню у поля ввода обновлено в MAX")
    return RedirectResponse("/admin/commands", status_code=303)
