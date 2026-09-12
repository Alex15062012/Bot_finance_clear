from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import db_session, render, require_admin
from app.config import get_settings
from app.db.models import BotCommandRow

router = APIRouter(
    prefix="/guide",
    tags=["admin-guide"],
)


@router.get("")
async def guide_page(
    request: Request,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
):
    settings = get_settings()
    commands = (
        await session.execute(
            select(BotCommandRow)
            .where(BotCommandRow.is_active.is_(True))
            .order_by(BotCommandRow.sort_order.asc(), BotCommandRow.id.asc())
        )
    ).scalars().all()
    return render(
        request,
        "guide.html",
        section="guide",
        title="Инструкция",
        bot_display_name=settings.bot_display_name,
        admin_public_url=settings.admin_public_url,
        bot_username=settings.bot_username,
        bot_commands=commands,
    )
