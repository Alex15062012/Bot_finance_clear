from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChatDirection(StrEnum):
    INBOUND = "inbound"  # от пользователя к админу
    OUTBOUND = "outbound"  # от админа к пользователю через бота


class ChatMessage(Base):
    """Переписка админа с пользователем через бота."""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    platform_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    admin_username: Mapped[str | None] = mapped_column(String(64))
    platform_message_id: Mapped[str | None] = mapped_column(String(128), index=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
