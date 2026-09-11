from __future__ import annotations

from typing import Any


def extract_user(update: dict[str, Any]) -> dict[str, Any] | None:
    if "user" in update and isinstance(update["user"], dict):
        return update["user"]
    message = update.get("message") or {}
    sender = message.get("sender")
    if isinstance(sender, dict):
        return sender
    callback = update.get("callback") or {}
    user = callback.get("user")
    if isinstance(user, dict):
        return user
    return None


def extract_chat_id(update: dict[str, Any]) -> int | None:
    """ID диалога/чата из Update (для лички с ботом — именно его нужно для POST /messages)."""
    chat_id = update.get("chat_id")
    if chat_id is not None:
        try:
            return int(chat_id)
        except (TypeError, ValueError):
            pass
    message = update.get("message") or {}
    recipient = message.get("recipient") or {}
    if recipient.get("chat_id") is not None:
        try:
            return int(recipient["chat_id"])
        except (TypeError, ValueError):
            pass
    return None


def extract_message_text(update: dict[str, Any]) -> str | None:
    message = update.get("message") or {}
    body = message.get("body") or {}
    text = body.get("text")
    return text if isinstance(text, str) else None


def extract_message_id(update: dict[str, Any]) -> str | None:
    message = update.get("message") or {}
    body = message.get("body") or {}
    mid = body.get("mid") or message.get("id") or body.get("seq")
    return str(mid) if mid is not None else None


def build_dedupe_key(update: dict[str, Any]) -> str:
    update_type = str(update.get("update_type", "unknown"))
    timestamp = update.get("timestamp", 0)
    user = extract_user(update) or {}
    user_id = user.get("user_id", "")
    chat_id = update.get("chat_id", "")
    message_id = extract_message_id(update) or ""
    payload = update.get("payload") or ""
    callback = update.get("callback") or {}
    callback_id = callback.get("callback_id") or ""
    return f"{update_type}:{timestamp}:{user_id}:{chat_id}:{message_id}:{payload}:{callback_id}"
