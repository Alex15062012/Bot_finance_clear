from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, UserState
from app.db.models.user import BotUsageStatus


class UserService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_platform_id(self, platform_user_id: int) -> User | None:
        result = await self.session.execute(
            select(User).where(User.platform_user_id == platform_user_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        platform_user_id: int,
        *,
        name: str | None = None,
        username: str | None = None,
        source: str | None = None,
        dialog_chat_id: int | None = None,
        mark_active: bool = True,
    ) -> tuple[User, bool]:
        user = await self.get_by_platform_id(platform_user_id)
        if user:
            changed = False
            if name and user.name != name:
                user.name = name
                changed = True
            if username and user.username != username:
                user.username = username
                changed = True
            if dialog_chat_id and user.dialog_chat_id != dialog_chat_id:
                user.dialog_chat_id = dialog_chat_id
                changed = True
            if mark_active and user.bot_status != BotUsageStatus.ACTIVE.value:
                user.bot_status = BotUsageStatus.ACTIVE.value
                user.blocked_at = None
                changed = True
            user.last_interaction_at = datetime.now(timezone.utc)
            if changed:
                await self.session.flush()
            return user, False

        user = User(
            platform_user_id=platform_user_id,
            name=name,
            username=username,
            source=source,
            dialog_chat_id=dialog_chat_id,
            state=UserState.NEW_SUBSCRIBER.value,
            bot_status=BotUsageStatus.ACTIVE.value,
            last_interaction_at=datetime.now(timezone.utc),
        )
        self.session.add(user)
        await self.session.flush()
        return user, True

    async def set_state(self, user: User, state: UserState | str) -> None:
        user.state = state.value if isinstance(state, UserState) else state
        user.last_interaction_at = datetime.now(timezone.utc)
        await self.session.flush()

    async def mark_blocked(self, user: User) -> None:
        user.bot_status = BotUsageStatus.BLOCKED.value
        user.blocked_at = datetime.now(timezone.utc)
        user.last_interaction_at = datetime.now(timezone.utc)
        await self.session.flush()

    async def mark_active(self, user: User) -> None:
        user.bot_status = BotUsageStatus.ACTIVE.value
        user.blocked_at = None
        user.last_interaction_at = datetime.now(timezone.utc)
        await self.session.flush()
