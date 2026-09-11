from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import RedirectResponse

from app.admin.paths import TEMPLATES_DIR
from app.config import get_settings
from app.db.session import get_session

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

SESSION_KEY = "admin_user"


class NotAuthenticatedError(Exception):
    """Пользователь не авторизован в админке."""


async def db_session() -> AsyncSession:
    async for session in get_session():
        yield session


def is_authenticated(request: Request) -> bool:
    return bool(request.session.get(SESSION_KEY))


def require_admin(request: Request) -> str:
    settings = get_settings()
    if not settings.admin_enabled:
        raise HTTPException(status_code=404, detail="Admin disabled")
    user = request.session.get(SESSION_KEY)
    if not user:
        raise NotAuthenticatedError()
    return str(user)


def login_user(request: Request, username: str) -> None:
    request.session[SESSION_KEY] = username


def logout_user(request: Request) -> None:
    request.session.clear()


def redirect_login() -> RedirectResponse:
    return RedirectResponse(
        url="/admin/login",
        status_code=303,
    )


NAV = [
    {"href": "/admin/", "label": "Обзор", "section": "dashboard"},
    {"href": "/admin/messages", "label": "Тексты", "section": "messages"},
    {"href": "/admin/commands", "label": "Меню /", "section": "commands"},
    {"href": "/admin/buttons", "label": "Кнопки", "section": "buttons"},
    {"href": "/admin/leads", "label": "Обращения", "section": "leads"},
    {"href": "/admin/materials", "label": "Материалы", "section": "materials"},
    {"href": "/admin/settings", "label": "Настройки", "section": "settings"},
    {"href": "/admin/users", "label": "Пользователи", "section": "users"},
]


def render(
    request: Request,
    template_name: str,
    *,
    section: str,
    title: str,
    status_code: int = 200,
    **context,
):
    settings = get_settings()
    return templates.TemplateResponse(
        request,
        template_name,
        {
            "title": title,
            "section": section,
            "nav": NAV,
            "flash": request.session.pop("flash", None),
            "bot_display_name": settings.bot_display_name,
            "admin_brand": f"Админ-панель бота «{settings.bot_display_name}»",
            **context,
        },
        status_code=status_code,
    )


def set_flash(request: Request, message: str, level: str = "ok") -> None:
    request.session["flash"] = {"message": message, "level": level}
