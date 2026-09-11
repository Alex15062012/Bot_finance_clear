from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import db_session, render, require_admin, set_flash
from app.db.models import Setting

# unused Form removed

router = APIRouter(
    prefix='/settings',
    tags=['admin-settings'],
)

# Ключи контента, которые можно править из админки (не секреты)
EDITABLE_KEYS = {
    "bot_display_name",
    "useful_materials_deeplink",
    "useful_materials_url",
    "personal_data_consent_enabled",
    "personal_data_consent_text",
    "personal_data_policy_url",
    "personal_data_document_version",
}


@router.get("")
async def list_settings(
    request: Request,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
):
    rows = (
        await session.execute(select(Setting).order_by(Setting.key.asc()))
    ).scalars().all()
    editable = [r for r in rows if r.key in EDITABLE_KEYS]
    return render(
        request,
        "settings/list.html",
        section="settings",
        title="Настройки контента",
        settings=editable,
    )


@router.post("")
async def save_settings(
    request: Request,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
):
    form = await request.form()
    rows = (
        await session.execute(select(Setting).where(Setting.key.in_(EDITABLE_KEYS)))
    ).scalars().all()
    by_key = {r.key: r for r in rows}

    changed = 0
    for key in EDITABLE_KEYS:
        if key not in form:
            continue
        value = str(form.get(key) or "")
        row = by_key.get(key)
        if not row:
            continue
        if row.value != value:
            row.value = value
            changed += 1

    await session.commit()
    set_flash(request, f"Сохранено изменений: {changed}")
    return RedirectResponse("/admin/settings", status_code=303)
