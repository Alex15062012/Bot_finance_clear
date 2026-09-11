from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, Boolean, DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserState(StrEnum):
    NEW_SUBSCRIBER = "new_subscriber"
    WELCOME_SENT = "welcome_sent"
    MATERIALS_REQUESTED = "materials_requested"
    BOT_OPENED = "bot_opened"
    MATERIALS_SENT = "materials_sent"
    AWAITING_QUESTION = "awaiting_question"
    QUESTION_RECEIVED = "question_received"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("platform_user_id", name="uq_users_platform_user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    platform_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    dialog_chat_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    name: Mapped[str | None] = mapped_column(String(255))
    username: Mapped[str | None] = mapped_column(String(255))
    source: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str] = mapped_column(String(64), default=UserState.NEW_SUBSCRIBER.value)

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    subscribed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_interaction_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    welcome_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    welcome_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    welcome_message_id: Mapped[str | None] = mapped_column(String(128))

    materials_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    materials_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    materials_request_pending: Mapped[bool] = mapped_column(Boolean, default=False)

    notes: Mapped[str | None] = mapped_column(Text)
