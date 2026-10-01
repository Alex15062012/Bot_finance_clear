from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import db_session, render, require_admin, set_flash
from app.db.models.channel_schedule import ChannelSchedule
from app.services.channel_broadcast import (
    MODE_LABELS,
    WEEKDAY_LABELS,
    describe_rule,
    parse_send_time,
)

router = APIRouter(prefix="/schedules", tags=["admin-schedules"])


@router.get("")
async def list_schedules(
    request: Request,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
):
    rows = (
        await session.execute(select(ChannelSchedule).order_by(ChannelSchedule.id.asc()))
    ).scalars().all()
    return render(
        request,
        "schedules/list.html",
        section="schedules",
        title="Расписание публикаций",
        schedules=rows,
        modes=MODE_LABELS,
        weekdays=list(enumerate(WEEKDAY_LABELS)),
        describe_rule=describe_rule,
    )


@router.post("")
async def add_schedule(
    request: Request,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
    mode: str = Form("daily"),
    weekday: str = Form(""),
    on_date: str = Form(""),
    send_time: str = Form(""),
):
    error = _apply(None, mode, weekday, on_date, send_time)
    if isinstance(error, str):
        set_flash(request, error, "error")
        return RedirectResponse("/admin/schedules", status_code=303)
    session.add(error)
    await session.commit()
    set_flash(request, "Правило добавлено")
    return RedirectResponse("/admin/schedules", status_code=303)


@router.post("/{schedule_id}/delete")
async def delete_schedule(
    schedule_id: int,
    request: Request,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
):
    row = await session.get(ChannelSchedule, schedule_id)
    if row is not None:
        await session.delete(row)
        await session.commit()
        set_flash(request, "Правило удалено")
    return RedirectResponse("/admin/schedules", status_code=303)


@router.post("/{schedule_id}")
async def update_schedule(
    schedule_id: int,
    request: Request,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
    mode: str = Form("daily"),
    weekday: str = Form(""),
    on_date: str = Form(""),
    send_time: str = Form(""),
    is_active: str = Form(""),
):
    row = await session.get(ChannelSchedule, schedule_id)
    if row is None:
        set_flash(request, "Правило не найдено", "error")
        return RedirectResponse("/admin/schedules", status_code=303)
    updated = _apply(row, mode, weekday, on_date, send_time)
    if isinstance(updated, str):
        set_flash(request, updated, "error")
        return RedirectResponse("/admin/schedules", status_code=303)
    row.is_active = is_active == "1"
    await session.commit()
    set_flash(request, "Правило сохранено")
    return RedirectResponse("/admin/schedules", status_code=303)


def _apply(
    row: ChannelSchedule | None,
    mode: str,
    weekday: str,
    on_date: str,
    send_time: str,
) -> ChannelSchedule | str:
    mode = (mode or "").strip()
    if mode not in MODE_LABELS:
        return "Выберите, как повторять публикацию"
    parsed = parse_send_time(send_time)
    if parsed is None:
        return "Укажите время в формате ЧЧ:ММ"
    hour, minute = parsed
    clock = f"{hour:02d}:{minute:02d}"
    day_index: int | None = None
    day_value = (on_date or "").strip()
    if mode == "weekday":
        try:
            day_index = int(weekday)
        except ValueError:
            return "Выберите день недели"
        if not 0 <= day_index <= 6:
            return "Выберите день недели"
        day_value = None
    elif mode == "date":
        if len(day_value) != 10 or day_value[4] != "-" or day_value[7] != "-":
            return "Укажите дату"
        day_index = None
    else:
        day_index = None
        day_value = None

    target = row or ChannelSchedule(is_active=True)
    target.mode = mode
    target.weekday = day_index
    target.on_date = day_value
    target.send_time = clock
    return target
