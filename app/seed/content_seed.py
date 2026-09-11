from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import BotCommandRow, Button, Material, MaterialType, MessageTemplate, Setting

WELCOME_TEXT = """{{name}}, здравствуйте! 😊 Спасибо, что подписались на мой канал.

Хочу не просто поприветствовать Вас, а сразу быть полезной.

Я собрала для подписчиков несколько практических материалов, которые помогают собственнику/руководителю быстро посмотреть на свои деньги и решения с другой стороны.

Чтобы получить материалы, нажмите кнопку ниже.

💡 Важно: материалы будут отправлены Вам не в канал, а в личный чат с ботом.

После нажатия кнопки откройте бот и нажмите «Начать», если платформа попросит это сделать. После запуска бот автоматически отправит Вам материалы."""

QUESTION_REQUEST_TEXT = """А если у вас сейчас есть конкретный вопрос по бизнесу — куда уходят деньги, как планировать налоги, где теряется прибыль, стоит ли делать покупку или инвестицию, как пережить финансово сложный период, как обучить сотрудников считать, как приготовить расчеты по проекту для банка или инвестора — напишите мне прямо сюда.

Можем разобрать ваш вопрос в короткой 30-минутной встрече и понять, где сейчас самая важная точка для работы.

Что сегодня в финансах вашего бизнеса волнует вас больше всего?

Можно одним предложением. Я начну с него. 💡"""

QUESTION_ACK_TEXT = """Спасибо! Я получила ваш вопрос и зафиксировала обращение.

Скоро вернусь к вам с ответом или предложением короткой встречи."""

MAIN_MENU_TEXT = """{{name}}, здравствуйте! 😊

Я бот канала «Про Финансы Ясно».

👇 Выберите действие кнопкой ниже.

💡 Чтобы открыть меню команд, нажмите «/» в поле ввода сообщения — появятся подсказки:
/materials — получить полезные материалы
/question — задать финансовый вопрос
/help — справка
/start — вернуться в это меню"""

HELP_TEXT = """Я помогаю подписчикам канала «Про Финансы Ясно».

Что умею сейчас:
• отправить полезные материалы в личный чат
• принять ваш финансовый вопрос и сохранить обращение

👇 Пользуйтесь кнопками ниже или меню команд.

💡 Нажмите «/» в поле ввода — откроется список команд:
/start — главное меню
/materials — получить материалы
/question — задать вопрос
/help — эта справка"""


async def seed_content(session: AsyncSession) -> None:
    """Идемпотентная заливка контента из ТЗ. Не затирает уже изменённые тексты."""
    from app.services.admin_users import ensure_default_admin

    await ensure_default_admin(session)

    settings = get_settings()
    deeplink = settings.materials_deeplink

    await _ensure_setting(
        session,
        "bot_display_name",
        settings.bot_display_name,
        "Название бота",
    )
    await _ensure_setting(
        session,
        "useful_materials_deeplink",
        deeplink,
        "Deep link для перехода в бот за материалами",
    )
    await _ensure_setting(
        session,
        "useful_materials_url",
        "https://max.ru/join/A2d7IV8Zes8LC4aNJ7BCPXxA2B1wy_tb0pnEgNUBGpo",
        "URL полезных материалов (отдельно от deep link)",
    )
    await _ensure_setting(
        session,
        "personal_data_consent_enabled",
        "false",
        "Включено ли согласие на обработку ПДн",
    )
    await _ensure_setting(
        session,
        "personal_data_consent_text",
        "",
        "Текст согласия (заготовка)",
    )
    await _ensure_setting(
        session,
        "personal_data_policy_url",
        "",
        "Ссылка на политику ПДн",
    )
    await _ensure_setting(
        session,
        "personal_data_document_version",
        "1.0",
        "Версия документа согласия",
    )

    await _ensure_message(
        session,
        code="new_subscriber_welcome",
        title="Приветствие нового подписчика",
        text=WELCOME_TEXT,
    )
    await _ensure_message(
        session,
        code="question_request",
        title="Запрос финансового вопроса после материалов",
        text=QUESTION_REQUEST_TEXT,
    )
    await _ensure_message(
        session,
        code="question_received_ack",
        title="Подтверждение получения вопроса",
        text=QUESTION_ACK_TEXT,
    )
    await _ensure_message(
        session,
        code="materials_intro",
        title="Вступление перед материалами (опционально)",
        text="Отправляю полезные материалы:",
    )
    await _upsert_message(
        session,
        code="bot_main_menu",
        title="Главное меню бота",
        text=MAIN_MENU_TEXT,
    )
    await _upsert_message(
        session,
        code="bot_help",
        title="Справка",
        text=HELP_TEXT,
    )

    await _ensure_button(
        session,
        code="useful_materials",
        title="👉 Получить полезные материалы",
        action_type="open_bot",
        url=deeplink,
        scenario="materials",
        payload=settings.materials_start_payload,
        sort_order=1,
    )
    await _ensure_button(
        session,
        code="menu_materials",
        title="📚 Получить материалы",
        action_type="callback",
        url=None,
        scenario="materials",
        payload="menu:materials",
        sort_order=10,
    )
    await _ensure_button(
        session,
        code="menu_question",
        title="❓ Задать вопрос",
        action_type="callback",
        url=None,
        scenario="question",
        payload="menu:question",
        sort_order=11,
    )
    await _ensure_button(
        session,
        code="menu_help",
        title="ℹ️ Помощь",
        action_type="callback",
        url=None,
        scenario="menu",
        payload="menu:help",
        sort_order=12,
    )

    for order, name, description in [
        (1, "start", "Главное меню"),
        (2, "materials", "Получить полезные материалы"),
        (3, "question", "Задать финансовый вопрос"),
        (4, "help", "Справка по боту"),
        (90, "admin", "Веб-админка (только для владельца)"),
    ]:
        await _ensure_bot_command(session, name=name, description=description, sort_order=order)

    materials_url = await _get_setting_value(session, "useful_materials_url")
    await _ensure_material(
        session,
        title="Материал №1",
        description="Практические материалы для собственника/руководителя",
        content_type=MaterialType.LINK.value,
        content="Подборка полезных материалов:",
        url=materials_url,
        sort_order=1,
    )
    await _ensure_material(
        session,
        title="Материал №2",
        description="Дополнительный материал (замените в админке/БД)",
        content_type=MaterialType.TEXT.value,
        content="Здесь можно разместить текст второго материала или заменить на документ/PDF.",
        url=None,
        sort_order=2,
    )

    await session.commit()


async def _get_setting_value(session: AsyncSession, key: str) -> str | None:
    result = await session.execute(select(Setting).where(Setting.key == key))
    row = result.scalar_one_or_none()
    return row.value if row else None


async def _ensure_setting(
    session: AsyncSession, key: str, value: str, description: str
) -> None:
    result = await session.execute(select(Setting).where(Setting.key == key))
    row = result.scalar_one_or_none()
    if row:
        return
    session.add(Setting(key=key, value=value, description=description))


async def _ensure_message(
    session: AsyncSession, *, code: str, title: str, text: str
) -> None:
    result = await session.execute(
        select(MessageTemplate).where(MessageTemplate.code == code)
    )
    if result.scalar_one_or_none():
        return
    session.add(MessageTemplate(code=code, title=title, text=text, version=1))


async def _upsert_message(
    session: AsyncSession, *, code: str, title: str, text: str
) -> None:
    """Обновляет служебные тексты меню (подсказка про «/» и т.п.)."""
    result = await session.execute(
        select(MessageTemplate).where(MessageTemplate.code == code)
    )
    row = result.scalar_one_or_none()
    if row:
        if row.text != text or row.title != title:
            row.title = title
            row.text = text
            row.version = int(row.version or 1) + 1
            row.is_active = True
        return
    session.add(MessageTemplate(code=code, title=title, text=text, version=1))


async def _ensure_button(
    session: AsyncSession,
    *,
    code: str,
    title: str,
    action_type: str,
    url: str | None,
    scenario: str | None,
    payload: str | None,
    sort_order: int,
) -> None:
    result = await session.execute(select(Button).where(Button.code == code))
    row = result.scalar_one_or_none()
    if row:
        # Кнопки меню всегда возвращаем в активное состояние при старте
        if code.startswith("menu_") and not row.is_active:
            row.is_active = True
        return
    session.add(
        Button(
            code=code,
            title=title,
            action_type=action_type,
            url=url,
            scenario=scenario,
            payload=payload,
            sort_order=sort_order,
        )
    )


async def _ensure_material(
    session: AsyncSession,
    *,
    title: str,
    description: str | None,
    content_type: str,
    content: str | None,
    url: str | None,
    sort_order: int,
) -> None:
    result = await session.execute(
        select(Material).where(
            Material.title == title,
            Material.sort_order == sort_order,
        )
    )
    if result.scalar_one_or_none():
        return
    session.add(
        Material(
            title=title,
            description=description,
            content_type=content_type,
            content=content,
            url=url,
            sort_order=sort_order,
            is_active=True,
        )
    )


async def _ensure_bot_command(
    session: AsyncSession,
    *,
    name: str,
    description: str,
    sort_order: int,
) -> None:
    result = await session.execute(select(BotCommandRow).where(BotCommandRow.name == name))
    if result.scalar_one_or_none():
        return
    session.add(
        BotCommandRow(
            name=name,
            description=description,
            sort_order=sort_order,
            is_active=True,
        )
    )
