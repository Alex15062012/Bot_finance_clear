from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import db_session, render, require_admin, set_flash
from app.db.models import LEAD_STATUS_LABELS, Lead, LeadStatus, User

router = APIRouter(
    prefix='/leads',
    tags=['admin-leads'],
)


@router.get("")
async def list_leads(
    request: Request,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
    status: str | None = None,
):
    stmt = select(Lead).order_by(Lead.created_at.desc())
    if status:
        stmt = stmt.where(Lead.status == status)
    leads = (await session.execute(stmt)).scalars().all()

    user_ids = {lead.user_id for lead in leads}
    users_map: dict[int, User] = {}
    if user_ids:
        users = (
            await session.execute(select(User).where(User.id.in_(user_ids)))
        ).scalars().all()
        users_map = {u.id: u for u in users}

    return render(
        request,
        "leads/list.html",
        section="leads",
        title="Обращения",
        leads=leads,
        users_map=users_map,
        status_filter=status,
        status_labels={s.value: label for s, label in LEAD_STATUS_LABELS.items()},
    )


@router.get("/{lead_id}")
async def lead_detail(
    lead_id: int,
    request: Request,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
):
    lead = await session.get(Lead, lead_id)
    if not lead:
        set_flash(request, "Обращение не найдено", "error")
        return RedirectResponse("/admin/leads", status_code=303)
    user = await session.get(User, lead.user_id)
    return render(
        request,
        "leads/detail.html",
        section="leads",
        title=f"Обращение #{lead.id}",
        lead=lead,
        user=user,
        status_labels={s.value: label for s, label in LEAD_STATUS_LABELS.items()},
    )


@router.post("/{lead_id}")
async def save_lead(
    lead_id: int,
    request: Request,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
    status: str = Form(...),
    assigned_to: str = Form(""),
    comment: str = Form(""),
):
    lead = await session.get(Lead, lead_id)
    if not lead:
        set_flash(request, "Обращение не найдено", "error")
        return RedirectResponse("/admin/leads", status_code=303)

    valid = {s.value for s in LeadStatus}
    if status not in valid:
        set_flash(request, "Некорректный статус", "error")
        return RedirectResponse(f"/admin/leads/{lead_id}", status_code=303)

    lead.status = status
    lead.assigned_to = assigned_to.strip() or None
    lead.comment = comment.strip() or None
    await session.commit()
    set_flash(request, "Обращение обновлено")
    return RedirectResponse(f"/admin/leads/{lead_id}", status_code=303)
