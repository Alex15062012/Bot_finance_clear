from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import db_session, render, require_admin
from app.db.models import Lead, LeadStatus, Material, MessageTemplate, User

router = APIRouter(tags=["admin-dashboard"])


@router.get("/")
async def dashboard(
    request: Request,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
):
    users_count = await session.scalar(select(func.count()).select_from(User)) or 0
    leads_count = await session.scalar(select(func.count()).select_from(Lead)) or 0
    new_leads = await session.scalar(
        select(func.count()).select_from(Lead).where(Lead.status == LeadStatus.NEW.value)
    ) or 0
    messages_count = await session.scalar(
        select(func.count()).select_from(MessageTemplate)
    ) or 0
    materials_count = await session.scalar(
        select(func.count()).select_from(Material).where(Material.is_active.is_(True))
    ) or 0

    recent = (
        await session.execute(select(Lead).order_by(Lead.created_at.desc()).limit(5))
    ).scalars().all()

    return render(
        request,
        "dashboard.html",
        section="dashboard",
        title="Обзор",
        stats={
            "users": users_count,
            "leads": leads_count,
            "new_leads": new_leads,
            "messages": messages_count,
            "materials": materials_count,
        },
        recent_leads=recent,
    )
