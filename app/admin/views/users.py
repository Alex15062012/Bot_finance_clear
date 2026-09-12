from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import db_session, render, require_admin, set_flash
from app.admin_access import is_bot_admin
from app.db.models import User
from app.services.admin_users import (
    deactivate_admin_for_bot_user,
    get_admin_for_bot_user,
    suggest_admin_login,
    upsert_admin_for_bot_user,
)

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
    panel_account = await get_admin_for_bot_user(session, user.id)
    return render(
        request,
        "users/detail.html",
        section="users",
        title=f"Пользователь #{user.id}",
        user=user,
        env_admin=is_bot_admin(user.platform_user_id, user=None),
        panel_account=panel_account,
        suggested_login=suggest_admin_login(user),
    )


@router.post("/{user_id}/admin")
async def set_user_admin(
    user_id: int,
    request: Request,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
    is_admin: str = Form("0"),
    login: str = Form(""),
    password: str = Form(""),
    password_confirm: str = Form(""),
):
    user = await session.get(User, user_id)
    if not user:
        set_flash(request, "Пользователь не найден", "error")
        return RedirectResponse("/admin/users", status_code=303)

    enabled = is_admin in {"1", "true", "on", "yes"}

    if enabled:
        login = (login or "").strip()
        password = password or ""
        password_confirm = password_confirm or ""
        if not login or not password:
            set_flash(
                request,
                "Укажите логин и пароль для входа в админ-панель",
                "error",
            )
            return RedirectResponse(f"/admin/users/{user.id}", status_code=303)
        if password != password_confirm:
            set_flash(request, "Пароль и подтверждение не совпадают", "error")
            return RedirectResponse(f"/admin/users/{user.id}", status_code=303)
        try:
            account = await upsert_admin_for_bot_user(
                session, user, username=login, password=password
            )
        except ValueError as exc:
            set_flash(request, str(exc), "error")
            return RedirectResponse(f"/admin/users/{user.id}", status_code=303)

        user.is_admin = True
        await session.commit()
        set_flash(
            request,
            f"Назначен администратором. Вход в панель: логин «{account.username}». "
            f"Команда /admin в боте тоже доступна.",
        )
        return RedirectResponse(f"/admin/users/{user.id}", status_code=303)

    user.is_admin = False
    await deactivate_admin_for_bot_user(session, user.id)
    await session.commit()

    note = ""
    if is_bot_admin(user.platform_user_id, user=None):
        note = (
            " Внимание: ID всё ещё в ADMIN_PLATFORM_USER_IDS — "
            "доступ к /admin в боте через .env сохранится."
        )
    set_flash(
        request,
        f"Роль администратора снята, вход в панель по этой учётке отключён.{note}",
        "ok" if not note else "error",
    )
    return RedirectResponse(f"/admin/users/{user.id}", status_code=303)


@router.post("/{user_id}/admin/password")
async def change_admin_password(
    user_id: int,
    request: Request,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(db_session),
    login: str = Form(""),
    password: str = Form(""),
    password_confirm: str = Form(""),
):
    """Смена логина/пароля уже назначенного администратора."""
    user = await session.get(User, user_id)
    if not user:
        set_flash(request, "Пользователь не найден", "error")
        return RedirectResponse("/admin/users", status_code=303)
    if not user.is_admin:
        set_flash(request, "Сначала назначьте пользователя администратором", "error")
        return RedirectResponse(f"/admin/users/{user.id}", status_code=303)

    login = (login or "").strip()
    if not login or not password:
        set_flash(request, "Укажите логин и новый пароль", "error")
        return RedirectResponse(f"/admin/users/{user.id}", status_code=303)
    if password != password_confirm:
        set_flash(request, "Пароль и подтверждение не совпадают", "error")
        return RedirectResponse(f"/admin/users/{user.id}", status_code=303)

    try:
        account = await upsert_admin_for_bot_user(
            session, user, username=login, password=password
        )
    except ValueError as exc:
        set_flash(request, str(exc), "error")
        return RedirectResponse(f"/admin/users/{user.id}", status_code=303)

    await session.commit()
    set_flash(
        request,
        f"Данные входа обновлены. Логин: «{account.username}».",
    )
    return RedirectResponse(f"/admin/users/{user.id}", status_code=303)
