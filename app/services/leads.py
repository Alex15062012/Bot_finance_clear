from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Lead, LeadStatus


class LeadService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_if_new(
        self,
        *,
        user_id: int,
        question: str,
        source: str | None = None,
        platform_message_id: str | None = None,
    ) -> tuple[Lead, bool]:
        if platform_message_id:
            result = await self.session.execute(
                select(Lead).where(Lead.platform_message_id == platform_message_id)
            )
            existing = result.scalar_one_or_none()
            if existing:
                return existing, False

        lead = Lead(
            user_id=user_id,
            question=question,
            status=LeadStatus.NEW.value,
            source=source or "materials_funnel",
            platform_message_id=platform_message_id,
        )
        self.session.add(lead)
        await self.session.flush()
        return lead, True
