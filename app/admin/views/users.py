from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import db_session, render, require_admin, set_flash
from app.admin_access import is_bot_admin
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
        set_flash(request, "Пользователь не найден", "error")
        return RedirectResponse("/admin/users", status_code=303)
    return render(
        request,
        "users/detail.html",
        section="users",
        title=f"Пользователь #{user.id}",
        user=user,
        env_admin=is_bot_admin(user.platform_user_id, user=None),
    )


@router.post("/{user_id}/admin")
async def set_user_admin(
    user_id: int,
    request: Request,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
    is_admin: str = Form("0"),
):
    user = await session.get(User, user_id)
    if not user:
        set_flash(request, "Пользователь не найден", "error")
        return RedirectResponse("/admin/users", status_code=303)

    enabled = is_admin in {"1", "true", "on", "yes"}
    user.is_admin = enabled
    await session.commit()

    if enabled:
        set_flash(
            request,
            f"Пользователь #{user.id} назначен администратором бота "
            f"(MAX id {user.platform_user_id}). Команда /admin станет доступна.",
        )
    else:
        note = ""
        if is_bot_admin(user.platform_user_id, user=None):
            note = (
                " Внимание: ID всё ещё в ADMIN_PLATFORM_USER_IDS — "
                "доступ к /admin через .env сохранится."
            )
        set_flash(
            request,
            f"С пользователя #{user.id} снята роль администратора в БД.{note}",
            "ok" if not note else "error",
        )
    return RedirectResponse(f"/admin/users/{user.id}", status_code=303)
