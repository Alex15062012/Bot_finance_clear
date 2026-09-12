from __future__ import annotations

from typing import Any

from app.config import Settings, get_settings


def parse_admin_ids(raw: str) -> set[int]:
    ids: set[int] = set()
    for part in (raw or "").replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            continue
    return ids


def is_bot_admin(
    platform_user_id: int,
    settings: Settings | None = None,
    *,
    user: Any | None = None,
) -> bool:
    """Админ бота: флаг users.is_admin в БД или ID из ADMIN_PLATFORM_USER_IDS."""
    if user is not None and bool(getattr(user, "is_admin", False)):
        return True
    settings = settings or get_settings()
    return platform_user_id in parse_admin_ids(settings.admin_platform_user_ids)


def admin_public_url(settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    return (settings.admin_public_url or "").rstrip("/") + "/"
