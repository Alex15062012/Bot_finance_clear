from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models.admin_user import AdminUser, hash_password, verify_password


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
