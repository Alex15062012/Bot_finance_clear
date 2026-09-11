from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.max_api.client import MaxApiClient
from app.max_api.types import build_dedupe_key
from app.scenarios.base import ScenarioContext
from app.scenarios.registry import build_scenarios
from app.services.content import ContentService
from app.services.events import EventService
from app.services.idempotency import IdempotencyService
from app.services.leads import LeadService
from app.services.messaging import MessagingService
from app.services.users import UserService

logger = logging.getLogger(__name__)


class UpdateRouter:
    def __init__(self, api: MaxApiClient):
        self.api = api
        self.scenarios = build_scenarios()

    async def handle(self, session: AsyncSession, update: dict[str, Any]) -> None:
        update_type = str(update.get("update_type", "unknown"))
        dedupe_key = build_dedupe_key(update)

        idempotency = IdempotencyService(session)
        claimed = await idempotency.try_claim(dedupe_key, update_type)
        if not claimed:
            logger.info("Skip duplicate update: %s", update_type)
            await session.commit()
            return

        users = UserService(session)
        content = ContentService(session)
        events = EventService(session)
        leads = LeadService(session)
        messaging = MessagingService(session, self.api, content)
        ctx = ScenarioContext(
            session=session,
            api=self.api,
            update=update,
            users=users,
            content=content,
            events=events,
            leads=leads,
            messaging=messaging,
        )

        try:
            handled = False
            for scenario in self.scenarios:
                if await scenario.handle(ctx):
                    handled = True
                    break
            if not handled:
                logger.debug("No scenario handled update_type=%s", update_type)
            await session.commit()
        except Exception:
            logger.exception("Error while handling update_type=%s", update_type)
            await session.rollback()
            # Ошибка одного пользователя не должна ронять процесс
