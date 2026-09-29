from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

TYPE_LABELS = {
    "chat": "Группа",
    "channel": "Канал",
}

STATUS_LABELS = {
    "active": "Бот добавлен",
    "removed": "Бот удалён",
}


class BotGroup(Base):
    """Группа или канал, куда бота добавили."""

    __tablename__ = "bot_groups"
    __table_args__ = (
        UniqueConstraint("platform_chat_id", name="uq_bot_groups_platform_chat_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    platform_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(255))
    chat_type: Mapped[str] = mapped_column(String(32), nullable=False, default="chat")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    link: Mapped[str | None] = mapped_column(String(512))
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    participants_count: Mapped[int | None] = mapped_column(Integer)
    added_by_user_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    added_by_name: Mapped[str | None] = mapped_column(String(255))
    added_by_username: Mapped[str | None] = mapped_column(String(255))
    added_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    @property
    def type_label(self) -> str:
        return TYPE_LABELS.get(self.chat_type, self.chat_type or "—")

    @property
    def status_label(self) -> str:
        return STATUS_LABELS.get(self.status, self.status)

    @property
    def added_at_label(self) -> str:
        if self.added_at is None:
            return "—"
        value = self.added_at
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone().strftime("%d.%m.%Y %H:%M")
