from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.max_api.client import MaxApiClient
from app.services.content import ContentService
from app.services.events import EventService
from app.services.leads import LeadService
from app.services.messaging import MessagingService
from app.services.users import UserService


@dataclass
class ScenarioContext:
    session: AsyncSession
    api: MaxApiClient
    update: dict[str, Any]
    users: UserService
    content: ContentService
    events: EventService
    leads: LeadService
    messaging: MessagingService


class Scenario(ABC):
    """Отдельный логический модуль воронки. Новые сценарии добавляются рядом."""

    code: str

    @abstractmethod
    async def handle(self, ctx: ScenarioContext) -> bool:
        """Возвращает True, если обновление обработано этим сценарием."""
