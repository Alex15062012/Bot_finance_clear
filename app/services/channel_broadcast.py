"""Публикации в каналы по расписанию из админки. Время — московское."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models.bot_group import BotGroup
from app.db.models.channel_broadcast import ChannelBroadcast
from app.db.models.channel_schedule import ChannelSchedule
from app.db.models.message import MessageTemplate
from app.max_api.client import MaxApiError, inline_keyboard, link_button

logger = logging.getLogger(__name__)

# Москва без перехода на летнее время: UTC+3. Не требует пакета tzdata.
MOSCOW = timezone(timedelta(hours=3))
# Если бот был выключен в точную минуту, публикация ещё уходит в этом окне.
GRACE = timedelta(minutes=30)
BUTTON_TITLE = "Задать финансовый вопрос"
WEEKDAY_LABELS = (
    "Понедельник",
    "Вторник",
    "Среда",
    "Четверг",
    "Пятница",
    "Суббота",
    "Воскресенье",
)
MODE_LABELS = {
    "daily": "Каждый день",
    "weekday": "День недели",
    "date": "Конкретная дата",
}

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


@dataclass(frozen=True)
class ScheduleRule:
    id: int | None
    mode: str
    weekday: int | None
    on_date: str | None
    hour: int
    minute: int


def as_moscow(now: datetime) -> datetime:
    if now.tzinfo is None:
        return now.replace(tzinfo=MOSCOW)
    return now.astimezone(MOSCOW)


def default_rules() -> list[ScheduleRule]:
    """Пока в админке нет ни одного правила — как раньше, каждый день в 10:00 и 16:00."""
    return [
        ScheduleRule(None, "daily", None, None, 10, 0),
        ScheduleRule(None, "daily", None, None, 16, 0),
    ]


def parse_send_time(value: str) -> tuple[int, int] | None:
    raw = (value or "").strip()
    parts = raw.split(":")
    if len(parts) < 2:
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def rule_from_row(row: ChannelSchedule) -> ScheduleRule | None:
    parsed = parse_send_time(row.send_time)
    if parsed is None:
        return None
    hour, minute = parsed
    return ScheduleRule(row.id, row.mode, row.weekday, row.on_date, hour, minute)


def due_slot_keys(now: datetime, rules: list[ScheduleRule]) -> list[str]:
    """Ключи слотов, которые пора отправить. Пусто, если ни одно правило не совпало."""
    local = as_moscow(now)
    keys: list[str] = []
    for rule in rules:
        if not _day_matches(rule, local.date(), local.weekday()):
            continue
        start = local.replace(hour=rule.hour, minute=rule.minute, second=0, microsecond=0)
        if not (timedelta(0) <= (local - start) < GRACE):
            continue
        ident = rule.id if rule.id is not None else f"default-{rule.hour:02d}{rule.minute:02d}"
        keys.append(f"{local.date().isoformat()}-{rule.hour:02d}{rule.minute:02d}-{ident}")
    return keys


def _day_matches(rule: ScheduleRule, day: date, weekday: int) -> bool:
    if rule.mode == "daily":
        return True
    if rule.mode == "weekday":
        return rule.weekday == weekday
    if rule.mode == "date":
        return rule.on_date == day.isoformat()
    return False


def describe_rule(rule: ChannelSchedule) -> str:
    clock = rule.send_time
    if rule.mode == "weekday" and rule.weekday is not None and 0 <= rule.weekday <= 6:
        return f"{WEEKDAY_LABELS[rule.weekday]}, {clock}"
    if rule.mode == "date" and rule.on_date:
        return f"{rule.on_date} {clock}"
    return f"{MODE_LABELS.get(rule.mode, rule.mode)}, {clock}"


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


async def load_rules(session: AsyncSession) -> list[ScheduleRule]:
    rows = (
        await session.execute(select(ChannelSchedule).order_by(ChannelSchedule.id.asc()))
    ).scalars().all()
    if not rows:
        return default_rules()
    rules: list[ScheduleRule] = []
    for row in rows:
        if not row.is_active:
            continue
        rule = rule_from_row(row)
        if rule is not None:
            rules.append(rule)
    return rules


async def send_due_broadcasts(
    session: AsyncSession,
    api,
    *,
    now: datetime | None = None,
) -> int:
    """Отправляет приглашение задать вопрос в каждый канал, если слот ещё не закрыт."""
    moment = now or datetime.now(MOSCOW)
    keys = due_slot_keys(moment, await load_rules(session))
    if not keys:
        return 0

    channels = await active_channel_ids(session)
    if not channels:
        return 0

    variants = await load_variants(session)
    button_url = get_settings().question_deeplink
    sent = 0
    for key in keys:
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
