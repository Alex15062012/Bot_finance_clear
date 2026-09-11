from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import db_session, render, require_admin
from app.db.models import User

router = APIRouter(
    prefix="/users",
    tags=["admin-users"],
)


@router.get("")
async def list_users(
    request: Request,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
):
    rows = (
        await session.execute(select(User).order_by(User.last_interaction_at.desc()))
    ).scalars().all()
    return render(
        request,
        "users/list.html",
        section="users",
        title="Пользователи",
        users=rows,
    )


@router.get("/{user_id}")
async def user_detail(
    user_id: int,
    request: Request,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
):
    user = await session.get(User, user_id)
    if not user:
        from fastapi.responses import RedirectResponse

        from app.admin.deps import set_flash

        set_flash(request, "Пользователь не найден", "error")
        return RedirectResponse("/admin/users", status_code=303)
    return render(
        request,
        "users/detail.html",
        section="users",
        title=f"Пользователь #{user.id}",
        user=user,
    )
