from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.models import UserState
from app.db.models.channel_welcome import ChannelWelcome
from app.max_api.client import MaxApiError
from app.max_api.types import extract_user, sent_message_mid
from app.scenarios.base import Scenario, ScenarioContext

logger = logging.getLogger(__name__)

# Два одинаковых user_added подряд не публикуют второе приветствие.
_REPEAT_GUARD = timedelta(minutes=2)


class NewSubscriberScenario(Scenario):
    code = "new_subscriber"

    async def handle(self, ctx: ScenarioContext) -> bool:
        update = ctx.update
        if update.get("update_type") != "user_added":
            return False

        chat_id = update.get("chat_id")
        if not await _is_tracked_membership(ctx, chat_id):
            logger.info("Skip user_added outside tracked chats chat_id=%s", chat_id)
            return True

        user_data = extract_user(update)
        if not user_data or user_data.get("is_bot"):
            return True

        platform_user_id = int(user_data["user_id"])
        user, created = await ctx.users.get_or_create(
            platform_user_id,
            name=user_data.get("name") or user_data.get("first_name"),
            username=user_data.get("username"),
            source="channel_subscribe",
        )
        if created:
            await ctx.events.track(
                "user_registered",
                user_id=user.id,
                platform_user_id=platform_user_id,
            )

        await ctx.events.track(
            "new_subscriber",
            user_id=user.id,
            platform_user_id=platform_user_id,
            payload={"chat_id": chat_id},
        )
        user.subscribed_at = user.subscribed_at or datetime.now(timezone.utc)
        kind = await _membership_kind(ctx, chat_id)
        nick = _subscriber_nick(user_data, user)

        if kind == "channel":
            previous = await _open_channel_welcome(ctx, platform_user_id, int(chat_id))
            if previous is not None and _welcome_is_fresh(previous):
                logger.info(
                    "Channel welcome already posted user=%s chat_id=%s",
                    platform_user_id,
                    chat_id,
                )
                return True
            await post_channel_welcome(ctx, user, platform_user_id, int(chat_id), nick)
            return True

        if user.welcome_sent:
            logger.info("Welcome already sent for user %s", platform_user_id)
            return True

        await deliver_materials_offer(ctx, user, platform_user_id, nick=nick)
        return True


def _subscriber_nick(user_data: dict, user) -> str:
    username = str(user_data.get("username") or user.username or "").strip().lstrip("@")
    if username:
        return f"@{username}"
    name = str(
        user_data.get("name") or user_data.get("first_name") or user.name or ""
    ).strip()
    return name or "друг"


async def post_channel_welcome(
    ctx: ScenarioContext,
    user,
    platform_user_id: int,
    chat_id: int,
    nick: str,
) -> bool:
    """Публикует приветствие в канале с кнопкой перехода в бота."""
    result = await ctx.messaging.safe_send_templated(
        platform_user_id,
        "new_subscriber_welcome",
        variables={"name": nick, "first_name": nick},
        button_codes=["useful_materials"],
        chat_id=chat_id,
    )
    if not result:
        logger.error(
            "Channel welcome not posted user=%s chat_id=%s",
            platform_user_id,
            chat_id,
        )
        return False

    message_id = sent_message_mid(result)
    if message_id:
        ctx.session.add(
            ChannelWelcome(
                platform_user_id=platform_user_id,
                platform_chat_id=chat_id,
                message_id=message_id,
            )
        )
    else:
        logger.error(
            "Channel welcome has no message id user=%s chat_id=%s",
            platform_user_id,
            chat_id,
        )

    user.welcome_sent = True
    user.welcome_sent_at = datetime.now(timezone.utc)
    user.welcome_message_id = message_id
    if user.state in {
        UserState.NEW_SUBSCRIBER.value,
        UserState.BOT_OPENED.value,
    }:
        await ctx.users.set_state(user, UserState.WELCOME_SENT)
    await ctx.events.track(
        "welcome_sent",
        user_id=user.id,
        platform_user_id=platform_user_id,
        payload={"chat_id": chat_id, "message_id": message_id, "where": "channel"},
    )
    await ctx.session.flush()
    return True


async def delete_channel_welcomes(ctx: ScenarioContext, platform_user_id: int) -> None:
    """Удаляет приветствия канала после того, как подписчик открыл бота."""
    rows = list(
        (
            await ctx.session.execute(
                select(ChannelWelcome).where(
                    ChannelWelcome.platform_user_id == platform_user_id,
                    ChannelWelcome.deleted_at.is_(None),
                )
            )
        ).scalars()
    )
    if not rows:
        return
    method = getattr(ctx.api, "delete_message", None)
    if method is None:
        logger.warning("Cannot delete channel welcome: API has no delete_message")
        return
    now = datetime.now(timezone.utc)
    for row in rows:
        try:
            await method(row.message_id)
        except MaxApiError as exc:
            logger.warning(
                "Channel welcome delete failed message_id=%s status=%s",
                row.message_id,
                exc.status_code,
            )
            continue
        except Exception:
            logger.exception("Channel welcome delete failed message_id=%s", row.message_id)
            continue
        row.deleted_at = now
    await ctx.session.flush()


def _welcome_is_fresh(row: ChannelWelcome) -> bool:
    created = row.created_at
    if created is None:
        return False
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - created < _REPEAT_GUARD


async def _open_channel_welcome(
    ctx: ScenarioContext, platform_user_id: int, chat_id: int
) -> ChannelWelcome | None:
    return (
        await ctx.session.execute(
            select(ChannelWelcome).where(
                ChannelWelcome.platform_user_id == platform_user_id,
                ChannelWelcome.platform_chat_id == chat_id,
                ChannelWelcome.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()


async def deliver_materials_offer(
    ctx: ScenarioContext,
    user,
    platform_user_id: int,
    *,
    nick: str | None = None,
) -> bool:
    """Личное предложение перейти в бота и получить материалы. False, если MAX не принял сообщение."""
    if user.welcome_sent:
        return False

    name = nick or user.name or "друг"
    result = await ctx.messaging.safe_send_templated(
        platform_user_id,
        "new_subscriber_welcome",
        variables={"name": name, "first_name": name},
        button_codes=["useful_materials"],
    )
    if not result:
        logger.error("Welcome not sent for user %s — state unchanged", platform_user_id)
        return False

    message_id = None
    if isinstance(result, dict):
        message = result.get("message") or result
        body = message.get("body") if isinstance(message, dict) else None
        if isinstance(body, dict):
            message_id = body.get("mid")
        elif isinstance(message, dict):
            message_id = message.get("id") or message.get("mid")

    user.welcome_sent = True
    user.welcome_sent_at = datetime.now(timezone.utc)
    user.welcome_message_id = str(message_id) if message_id else None
    if user.state in {
        UserState.NEW_SUBSCRIBER.value,
        UserState.BOT_OPENED.value,
    }:
        await ctx.users.set_state(user, UserState.WELCOME_SENT)
    await ctx.events.track(
        "welcome_sent",
        user_id=user.id,
        platform_user_id=platform_user_id,
        payload={"message_id": user.welcome_message_id},
    )
    return True


async def _is_tracked_membership(ctx: ScenarioContext, chat_id) -> bool:
    return await _membership_kind(ctx, chat_id) is not None


async def _membership_kind(ctx: ScenarioContext, chat_id) -> str | None:
    """channel или chat, если бот там администратор."""
    from app.config import get_settings
    from app.services.bot_groups import get_by_chat_id

    try:
        cid = int(chat_id)
    except (TypeError, ValueError):
        return None

    settings = get_settings()
    if settings.channel_chat_id and cid == int(settings.channel_chat_id):
        return "channel"

    row = await get_by_chat_id(ctx.session, cid)
    if row is None or row.status != "active":
        return None
    if row.chat_type == "channel":
        return "channel"
    if row.chat_type == "chat":
        return "chat"
    return None
