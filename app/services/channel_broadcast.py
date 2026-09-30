"""Публикации в каналы, куда бот добавлен: 10:00 и 16:00 по Москве."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models.bot_group import BotGroup
from app.db.models.channel_broadcast import ChannelBroadcast
from app.db.models.message import MessageTemplate
from app.max_api.client import MaxApiError, inline_keyboard, link_button

logger = logging.getLogger(__name__)

# Москва без перехода на летнее время: UTC+3. Не требует пакета tzdata.
MOSCOW = timezone(timedelta(hours=3))
BROADCAST_HOURS = (10, 16)
BUTTON_TITLE = "Задать финансовый вопрос"

CHANNEL_QUESTION_VARIANTS = (
    "Есть вопрос по финансам бизнеса? Задайте его владельцу канала: "
    "куда уходят деньги, как считать прибыль и что делать дальше.\n\n"
    "Нажмите кнопку и напишите вопрос в боте.",
    "Владелец канала разбирает финансовые вопросы подписчиков лично. "
    "Опишите свою ситуацию в боте — одного сообщения достаточно, чтобы начать.",
    "Не откладывайте вопрос про налоги, прибыль или кассовый разрыв. "
    "Перейдите в бота и задайте его владельцу канала.",
    "Короткий финансовый вопрос часто экономит месяцы лишних решений. "
    "Напишите владельцу канала через бота, что сейчас беспокоит больше всего.",
)

_VARIANT_CODES = tuple(
    f"channel_question_{index}" for index in range(1, len(CHANNEL_QUESTION_VARIANTS) + 1)
)


def slot_key(now: datetime) -> str | None:
    """Ключ слота, если сейчас час публикации по Москве. Иначе None."""
    if now.tzinfo is None:
        local = now.replace(tzinfo=MOSCOW)
    else:
        local = now.astimezone(MOSCOW)
    if local.hour not in BROADCAST_HOURS:
        return None
    return f"{local.date().isoformat()}-{local.hour:02d}"


def variant_index(sent_before: int, total: int) -> int:
    if total <= 0:
        return 0
    return sent_before % total


async def active_channel_ids(session: AsyncSession) -> list[int]:
    """Каналы, где бот сейчас администратор. Плюс CHANNEL_CHAT_ID, если задан."""
    rows = (
        await session.execute(
            select(BotGroup.platform_chat_id).where(
                BotGroup.status == "active",
                BotGroup.chat_type == "channel",
            )
        )
    ).scalars().all()
    ids = [int(chat_id) for chat_id in rows]
    settings = get_settings()
    if settings.channel_chat_id and int(settings.channel_chat_id) not in ids:
        ids.append(int(settings.channel_chat_id))
    return ids


async def load_variants(session: AsyncSession) -> list[str]:
    rows = (
        await session.execute(
            select(MessageTemplate)
            .where(
                MessageTemplate.code.in_(_VARIANT_CODES),
                MessageTemplate.is_active.is_(True),
            )
            .order_by(MessageTemplate.code.asc())
        )
    ).scalars().all()
    texts = [row.text.strip() for row in rows if row.text and row.text.strip()]
    return texts or list(CHANNEL_QUESTION_VARIANTS)


async def send_due_broadcasts(
    session: AsyncSession,
    api,
    *,
    now: datetime | None = None,
) -> int:
    """Отправляет приглашение задать вопрос в каждый канал, если слот ещё не закрыт."""
    moment = now or datetime.now(MOSCOW)
    key = slot_key(moment)
    if key is None:
        return 0

    channels = await active_channel_ids(session)
    if not channels:
        return 0

    variants = await load_variants(session)
    button_url = get_settings().question_deeplink
    sent = 0
    for chat_id in channels:
        if await _already_sent(session, chat_id, key):
            continue
        index = variant_index(await _sent_count(session, chat_id), len(variants))
        text = variants[index]
        if not await _claim_slot(session, chat_id, key, index):
            continue
        try:
            await _post(api, chat_id, text, button_url)
        except Exception:
            logger.exception("Channel invite failed chat_id=%s slot=%s", chat_id, key)
            await _release_slot(session, chat_id, key)
            continue
        sent += 1
        logger.info("Channel invite sent chat_id=%s slot=%s variant=%s", chat_id, key, index)
    return sent


async def _already_sent(session: AsyncSession, chat_id: int, key: str) -> bool:
    found = await session.scalar(
        select(ChannelBroadcast.id).where(
            ChannelBroadcast.platform_chat_id == chat_id,
            ChannelBroadcast.slot_key == key,
        )
    )
    return found is not None


async def _sent_count(session: AsyncSession, chat_id: int) -> int:
    count = await session.scalar(
        select(func.count(ChannelBroadcast.id)).where(
            ChannelBroadcast.platform_chat_id == chat_id
        )
    )
    return int(count or 0)


async def _claim_slot(
    session: AsyncSession, chat_id: int, key: str, index: int
) -> bool:
    try:
        async with session.begin_nested():
            session.add(
                ChannelBroadcast(
                    platform_chat_id=chat_id,
                    slot_key=key,
                    variant_index=index,
                )
            )
            await session.flush()
    except IntegrityError:
        return False
    return True


async def _release_slot(session: AsyncSession, chat_id: int, key: str) -> None:
    row = await session.scalar(
        select(ChannelBroadcast).where(
            ChannelBroadcast.platform_chat_id == chat_id,
            ChannelBroadcast.slot_key == key,
        )
    )
    if row is not None:
        await session.delete(row)
        await session.flush()


async def _post(api, chat_id: int, text: str, button_url: str) -> None:
    attachments = None
    if button_url:
        attachments = [
            inline_keyboard([[link_button(BUTTON_TITLE, button_url)]])
        ]
    try:
        await api.send_message_to_chat(
            chat_id,
            text,
            attachments=attachments,
            format=None,
        )
    except MaxApiError:
        raise
