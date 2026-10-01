"""Группы и каналы, в которые добавлен бот."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.bot_group import BotGroup
from app.max_api.client import MaxApiError

logger = logging.getLogger(__name__)

_REMOVED_STATUSES = frozenset({"removed", "left", "closed"})


def chat_meta_from_update(update: dict[str, Any]) -> dict[str, Any] | None:
    message = update.get("message") if isinstance(update.get("message"), dict) else {}
    recipient = message.get("recipient") if isinstance(message.get("recipient"), dict) else {}
    raw_id = update.get("chat_id")
    if raw_id is None:
        raw_id = recipient.get("chat_id")
    if raw_id is None:
        return None
    try:
        chat_id = int(raw_id)
    except (TypeError, ValueError):
        return None

    chat_type = recipient.get("chat_type") or update.get("chat_type")
    if update.get("is_channel") is True:
        chat_type = "channel"
    elif update.get("is_channel") is False and chat_type not in {"chat", "channel"}:
        chat_type = "chat"
    if isinstance(chat_type, str):
        chat_type = chat_type.lower()
    else:
        chat_type = None
    return {"chat_id": chat_id, "chat_type": chat_type}


def _event_time(update: dict[str, Any]) -> datetime:
    raw = update.get("timestamp")
    if isinstance(raw, (int, float)) and raw > 0:
        seconds = raw / 1000 if raw > 10_000_000_000 else raw
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    return datetime.now(timezone.utc)


def _adder(update: dict[str, Any]) -> dict[str, Any]:
    user = update.get("user")
    return user if isinstance(user, dict) else {}


def apply_api_chat(row: BotGroup, chat: dict[str, Any]) -> bool:
    """Заполняет строку из GET /chats/{id}. Личный диалог не храним."""
    kind = str(chat.get("type") or "")
    if kind == "dialog":
        return False
    if kind in {"chat", "channel"}:
        row.chat_type = kind
    title = chat.get("title")
    if isinstance(title, str) and title.strip():
        row.title = title.strip()[:255]
    link = chat.get("link")
    if isinstance(link, str) and link.strip():
        row.link = link.strip()[:512]
    count = chat.get("participants_count")
    if isinstance(count, int):
        row.participants_count = count
    row.is_public = bool(chat.get("is_public"))
    status = str(chat.get("status") or "")
    if status in _REMOVED_STATUSES:
        row.status = "removed"
        if row.removed_at is None:
            row.removed_at = datetime.now(timezone.utc)
    elif status == "active":
        row.status = "active"
        row.removed_at = None
    return True


async def list_groups(session: AsyncSession) -> list[BotGroup]:
    rows = (
        await session.execute(
            select(BotGroup).order_by(
                BotGroup.status.asc(),
                BotGroup.added_at.desc(),
                BotGroup.id.desc(),
            )
        )
    ).scalars().all()
    return list(rows)


async def get_by_chat_id(session: AsyncSession, chat_id: int) -> BotGroup | None:
    return (
        await session.execute(
            select(BotGroup).where(BotGroup.platform_chat_id == chat_id)
        )
    ).scalar_one_or_none()


def _mark_removed(row: BotGroup) -> None:
    row.status = "removed"
    if row.removed_at is None:
        row.removed_at = datetime.now(timezone.utc)


def _access_lost(exc: MaxApiError) -> bool:
    body = str(exc.body or "").lower()
    if exc.status_code in {403, 404}:
        return True
    return any(
        code in body
        for code in (
            "chat.not.found",
            "chat.denied",
            "chat.forbidden",
            "chat.not.member",
        )
    )


def _admin_user_ids(payload: Any) -> list[int] | None:
    members: Any = payload
    if isinstance(payload, dict):
        members = payload.get("members") or payload.get("admins") or payload.get("users")
    if not isinstance(members, list):
        return None
    ids: list[int] = []
    for item in members:
        if not isinstance(item, dict):
            continue
        user_id = item.get("user_id")
        if user_id is None and isinstance(item.get("user"), dict):
            user_id = item["user"].get("user_id")
        if user_id is None:
            continue
        try:
            ids.append(int(user_id))
        except (TypeError, ValueError):
            continue
    return ids


async def _bot_user_id(api: Any) -> int | None:
    method = getattr(api, "get_me", None)
    if method is None:
        return None
    try:
        me = await method()
    except Exception:
        logger.exception("Не удалось прочитать профиль бота")
        return None
    if isinstance(me, dict) and me.get("user_id") is not None:
        try:
            return int(me["user_id"])
        except (TypeError, ValueError):
            return None
    return None


async def _bot_is_admin(api: Any, chat_id: int, bot_user_id: int) -> bool | None:
    """True — бот в администраторах, False — уже нет, None — MAX не ответил определённо."""
    method = getattr(api, "get_chat_admins", None)
    if method is None:
        return None
    try:
        payload = await method(int(chat_id))
    except MaxApiError as exc:
        if _access_lost(exc):
            return False
        return None
    except Exception:
        logger.exception("Не удалось прочитать администраторов чата %s", chat_id)
        return None
    ids = _admin_user_ids(payload)
    if ids is None:
        return None
    return bot_user_id in ids


async def _enrich(
    session: AsyncSession,
    api: Any,
    row: BotGroup,
    *,
    bot_user_id: int | None = None,
) -> BotGroup | None:
    if api is None:
        return row
    try:
        chat = await api.get_chat(int(row.platform_chat_id))
    except MaxApiError as exc:
        if _access_lost(exc):
            _mark_removed(row)
            return row
        logger.warning(
            "Не удалось прочитать чат %s: %s",
            row.platform_chat_id,
            exc.status_code,
        )
        return row
    except Exception:
        logger.exception("Не удалось прочитать чат %s", row.platform_chat_id)
        return row
    if not isinstance(chat, dict):
        return row
    if not apply_api_chat(row, chat):
        await session.delete(row)
        await session.flush()
        return None
    if row.status == "active" and bot_user_id is not None:
        still_admin = await _bot_is_admin(api, int(row.platform_chat_id), bot_user_id)
        if still_admin is False:
            _mark_removed(row)
    return row


async def remember_bot_added(
    session: AsyncSession,
    update: dict[str, Any],
    api: Any = None,
) -> BotGroup | None:
    meta = chat_meta_from_update(update)
    if meta is None:
        return None
    chat_id = int(meta["chat_id"])
    row = await get_by_chat_id(session, chat_id)
    if row is None:
        row = BotGroup(platform_chat_id=chat_id, chat_type=meta["chat_type"] or "chat")
        session.add(row)
    row.status = "active"
    row.removed_at = None
    if meta["chat_type"] in {"chat", "channel"}:
        row.chat_type = meta["chat_type"]
    adder = _adder(update)
    user_id = adder.get("user_id")
    if user_id is not None:
        try:
            row.added_by_user_id = int(user_id)
        except (TypeError, ValueError):
            pass
    name = adder.get("name") or adder.get("first_name")
    if isinstance(name, str) and name.strip():
        row.added_by_name = name.strip()[:255]
    username = adder.get("username")
    if isinstance(username, str) and username.strip():
        row.added_by_username = username.strip()[:255]
    if row.added_at is None:
        row.added_at = _event_time(update)
    await session.flush()
    return await _enrich(session, api, row)


async def remember_bot_removed(
    session: AsyncSession,
    update: dict[str, Any],
    api: Any = None,
) -> BotGroup | None:
    meta = chat_meta_from_update(update)
    if meta is None:
        return None
    chat_id = int(meta["chat_id"])
    row = await get_by_chat_id(session, chat_id)
    if row is None:
        row = BotGroup(
            platform_chat_id=chat_id,
            chat_type=meta["chat_type"] or "chat",
            added_at=_event_time(update),
        )
        session.add(row)
    if meta["chat_type"] in {"chat", "channel"}:
        row.chat_type = meta["chat_type"]
    await session.flush()
    row = await _enrich(session, api, row)
    if row is None:
        return None
    row.status = "removed"
    row.removed_at = _event_time(update)
    await session.flush()
    return row


async def remember_seen_chat(
    session: AsyncSession,
    update: dict[str, Any],
    api: Any = None,
) -> BotGroup | None:
    """Запоминает группу или канал, если бот уже состоит в нём и пришло событие."""
    update_type = str(update.get("update_type") or "")
    meta = chat_meta_from_update(update)
    if meta is None:
        return None
    kind = meta["chat_type"]
    if kind == "dialog":
        return None
    if kind not in {"chat", "channel"}:
        if update_type not in {"user_added", "user_removed"}:
            return None
    chat_id = int(meta["chat_id"])
    existing = await get_by_chat_id(session, chat_id)
    if existing is not None:
        return existing
    row = BotGroup(
        platform_chat_id=chat_id,
        chat_type=kind or "chat",
        status="active",
        added_at=_event_time(update),
    )
    session.add(row)
    await session.flush()
    return await _enrich(session, api, row)


async def refresh_groups(session: AsyncSession, api: Any) -> None:
    """Заново читает каждый известный чат и снимает те, где бот уже не администратор."""
    bot_user_id = await _bot_user_id(api)
    rows = await list_groups(session)
    for row in rows:
        await _enrich(session, api, row, bot_user_id=bot_user_id)
    await session.flush()


async def sync_groups_from_api(session: AsyncSession, api: Any) -> int:
    """Перепроверяет права бота в уже найденных чатах.

    Новые каналы и группы попадают в список из событий бота (добавление,
    сообщение, новый подписчик). Повторный обход старой очереди MAX
    пропускает события и не возвращает их, поэтому кнопка «Обновить»
    очередь не читает.
    """
    await refresh_groups(session, api)
    return len(await list_groups(session))
