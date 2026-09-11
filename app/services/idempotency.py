from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ProcessedUpdate


class IdempotencyService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def try_claim(self, dedupe_key: str, update_type: str) -> bool:
        """Возвращает True, если событие новое и можно обрабатывать."""
        result = await self.session.execute(
            select(ProcessedUpdate.id).where(ProcessedUpdate.dedupe_key == dedupe_key)
        )
        if result.scalar_one_or_none() is not None:
            return False

        self.session.add(ProcessedUpdate(dedupe_key=dedupe_key, update_type=update_type))
        await self.session.flush()
        return True
