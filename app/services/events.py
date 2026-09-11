from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Event


class EventService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def track(
        self,
        event_type: str,
        *,
        user_id: int | None = None,
        platform_user_id: int | None = None,
        payload: dict[str, Any] | str | None = None,
    ) -> Event:
        if isinstance(payload, dict):
            payload_str = json.dumps(payload, ensure_ascii=False)
        else:
            payload_str = payload
        event = Event(
            event_type=event_type,
            user_id=user_id,
            platform_user_id=platform_user_id,
            payload=payload_str,
        )
        self.session.add(event)
        await self.session.flush()
        return event
