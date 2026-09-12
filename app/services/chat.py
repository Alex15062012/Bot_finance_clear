from __future__ import annotations

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat_message import ChatDirection, ChatMessage
from app.db.models.user import User


class ChatService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_inbound(
        self,
        *,
        user_id: int,
        platform_user_id: int,
        text: str,
        platform_message_id: str | None = None,
    ) -> ChatMessage | None:
        if platform_message_id:
            existing = await self.session.execute(
                select(ChatMessage).where(
                    ChatMessage.platform_message_id == platform_message_id,
                    ChatMessage.direction == ChatDirection.INBOUND.value,
                )
            )
            if existing.scalar_one_or_none():
                return None

        row = ChatMessage(
            user_id=user_id,
            platform_user_id=platform_user_id,
            direction=ChatDirection.INBOUND.value,
            text=text.strip(),
            platform_message_id=platform_message_id,
            is_read=False,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def add_outbound(
        self,
        *,
        user_id: int,
        platform_user_id: int,
        text: str,
        admin_username: str,
        platform_message_id: str | None = None,
    ) -> ChatMessage:
        row = ChatMessage(
            user_id=user_id,
            platform_user_id=platform_user_id,
            direction=ChatDirection.OUTBOUND.value,
            text=text.strip(),
            admin_username=admin_username,
            platform_message_id=platform_message_id,
            is_read=True,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def list_for_user(self, user_id: int, *, limit: int = 200) -> list[ChatMessage]:
        rows = (
            await self.session.execute(
                select(ChatMessage)
                .where(ChatMessage.user_id == user_id)
                .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
                .limit(limit)
            )
        ).scalars().all()
        return list(rows)

    async def mark_inbound_read(self, user_id: int) -> None:
        rows = (
            await self.session.execute(
                select(ChatMessage).where(
                    ChatMessage.user_id == user_id,
                    ChatMessage.direction == ChatDirection.INBOUND.value,
                    ChatMessage.is_read.is_(False),
                )
            )
        ).scalars().all()
        for row in rows:
            row.is_read = True
        if rows:
            await self.session.flush()

    async def recent_threads(self, *, limit: int = 50) -> list[dict]:
        """Пользователи с последним сообщением и числом непрочитанных."""
        last_subq = (
            select(
                ChatMessage.user_id.label("user_id"),
                func.max(ChatMessage.id).label("last_id"),
            )
            .group_by(ChatMessage.user_id)
            .subquery()
        )
        unread_subq = (
            select(
                ChatMessage.user_id.label("user_id"),
                func.count(ChatMessage.id).label("unread"),
            )
            .where(
                ChatMessage.direction == ChatDirection.INBOUND.value,
                ChatMessage.is_read.is_(False),
            )
            .group_by(ChatMessage.user_id)
            .subquery()
        )

        result = await self.session.execute(
            select(User, ChatMessage, unread_subq.c.unread)
            .join(last_subq, last_subq.c.user_id == User.id)
            .join(ChatMessage, ChatMessage.id == last_subq.c.last_id)
            .outerjoin(unread_subq, unread_subq.c.user_id == User.id)
            .order_by(desc(ChatMessage.created_at))
            .limit(limit)
        )
        threads: list[dict] = []
        for user, last_msg, unread in result.all():
            threads.append(
                {
                    "user": user,
                    "last_message": last_msg,
                    "unread": int(unread or 0),
                }
            )
        return threads
