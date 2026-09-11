from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Button, Material, MessageTemplate, Setting


class ContentService:
    """Слой контента: тексты, кнопки, материалы, настройки сценариев."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_setting(self, key: str, default: str | None = None) -> str | None:
        result = await self.session.execute(select(Setting).where(Setting.key == key))
        row = result.scalar_one_or_none()
        return row.value if row else default

    async def get_bool_setting(self, key: str, default: bool = False) -> bool:
        value = await self.get_setting(key)
        if value is None:
            return default
        return value.strip().lower() in {"1", "true", "yes", "on"}

    async def get_message(self, code: str) -> MessageTemplate | None:
        result = await self.session.execute(
            select(MessageTemplate).where(
                MessageTemplate.code == code,
                MessageTemplate.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def get_button(self, code: str) -> Button | None:
        result = await self.session.execute(
            select(Button).where(Button.code == code, Button.is_active.is_(True))
        )
        return result.scalar_one_or_none()

    async def get_menu_button_codes(self) -> list[str]:
        """Кнопки главного меню: code начинается с menu_, порядок из БД."""
        result = await self.session.execute(
            select(Button.code)
            .where(
                Button.is_active.is_(True),
                Button.code.like("menu_%"),
            )
            .order_by(Button.sort_order.asc(), Button.id.asc())
        )
        codes = list(result.scalars().all())
        return codes or ["menu_materials", "menu_question", "menu_help"]

    async def get_active_materials(self) -> list[Material]:
        result = await self.session.execute(
            select(Material)
            .where(Material.is_active.is_(True))
            .order_by(Material.sort_order.asc(), Material.id.asc())
        )
        return list(result.scalars().all())
