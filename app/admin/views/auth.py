from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.deps import (
    db_session,
    is_authenticated,
    login_user,
    logout_user,
    redirect_login,
    render,
    set_flash,
)
from app.config import reload_settings
from app.services.admin_users import authenticate_admin, ensure_default_admin

router = APIRouter(tags=["admin-auth"])


@router.get("/login")
async def login_page(request: Request):
    if is_authenticated(request):
        return RedirectResponse("/admin/", status_code=303)
    return render(
        request,
        "login.html",
        section="login",
        title="Вход",
        error=None,
    )


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    session: AsyncSession = Depends(db_session),
):
    reload_settings()
    await ensure_default_admin(session)
    user = await authenticate_admin(session, username, password)
    if user:
        await session.commit()
        login_user(request, user.username)
        set_flash(request, "Вы вошли в админку")
        return RedirectResponse("/admin/", status_code=303)

    await session.rollback()
    return render(
        request,
        "login.html",
        section="login",
        title="Вход",
        error="Неверный логин или пароль",
        status_code=401,
    )


@router.post("/logout")
async def logout(request: Request):
    logout_user(request)
    return redirect_login()
