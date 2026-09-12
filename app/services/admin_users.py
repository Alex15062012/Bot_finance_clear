from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models.admin_user import AdminUser, hash_password, verify_password
from app.db.models.user import User

_LOGIN_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,64}$")


def suggest_admin_login(user: User) -> str:
    raw = (user.username or "").strip().lstrip("@")
    if raw and _LOGIN_RE.match(raw):
        return raw.lower()
    return f"user_{user.platform_user_id}"


def validate_admin_credentials(username: str, password: str) -> str | None:
    username = username.strip()
    if not _LOGIN_RE.match(username):
        return (
            "Логин: 3–64 символа, латиница, цифры, точка, _ или -. "
            "Без пробелов и кириллицы."
        )
    if len(password) < 6:
        return "Пароль должен быть не короче 6 символов."
    return None


async def ensure_default_admin(session: AsyncSession) -> AdminUser:
    """Создаёт/обновляет пользователя admin из .env (по умолчанию admin/admin123)."""
    settings = get_settings()
    username = (settings.admin_username or "admin").strip()
    password = settings.admin_password or "admin123"

    result = await session.execute(
        select(AdminUser).where(AdminUser.username == username)
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = AdminUser(
            username=username,
            password_hash=hash_password(password),
            is_active=True,
        )
        session.add(row)
        await session.flush()
        return row

    # Если пароль из .env не подходит к текущему hash — синхронизируем
    if not verify_password(password, row.password_hash):
        row.password_hash = hash_password(password)
        row.is_active = True
        await session.flush()
    return row


async def authenticate_admin(
    session: AsyncSession, username: str, password: str
) -> AdminUser | None:
    result = await session.execute(
        select(AdminUser).where(
            AdminUser.username == username.strip(),
            AdminUser.is_active.is_(True),
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        return None
    if not verify_password(password, row.password_hash):
        return None
    return row


async def get_admin_for_bot_user(
    session: AsyncSession, bot_user_id: int
) -> AdminUser | None:
    result = await session.execute(
        select(AdminUser).where(AdminUser.bot_user_id == bot_user_id)
    )
    return result.scalar_one_or_none()


async def upsert_admin_for_bot_user(
    session: AsyncSession,
    user: User,
    *,
    username: str,
    password: str,
) -> AdminUser:
    """Создаёт или обновляет учётку входа в панель для пользователя бота."""
    username = username.strip()
    error = validate_admin_credentials(username, password)
    if error:
        raise ValueError(error)

    # Уже занят другим человеком?
    by_login = (
        await session.execute(select(AdminUser).where(AdminUser.username == username))
    ).scalar_one_or_none()
    linked = await get_admin_for_bot_user(session, user.id)

    if by_login and linked and by_login.id != linked.id:
        raise ValueError(f"Логин «{username}» уже занят.")
    if by_login and not linked and by_login.bot_user_id not in (None, user.id):
        raise ValueError(f"Логин «{username}» уже занят.")

    row = linked or by_login
    if row is None:
        row = AdminUser(
            username=username,
            password_hash=hash_password(password),
            is_active=True,
            bot_user_id=user.id,
            platform_user_id=user.platform_user_id,
        )
        session.add(row)
    else:
        # Смена логина — проверить уникальность
        if row.username != username:
            clash = (
                await session.execute(
                    select(AdminUser).where(
                        AdminUser.username == username,
                        AdminUser.id != row.id,
                    )
                )
            ).scalar_one_or_none()
            if clash:
                raise ValueError(f"Логин «{username}» уже занят.")
            row.username = username
        row.password_hash = hash_password(password)
        row.is_active = True
        row.bot_user_id = user.id
        row.platform_user_id = user.platform_user_id

    await session.flush()
    return row


async def deactivate_admin_for_bot_user(
    session: AsyncSession, bot_user_id: int
) -> AdminUser | None:
    row = await get_admin_for_bot_user(session, bot_user_id)
    if not row:
        return None
    row.is_active = False
    await session.flush()
    return row
