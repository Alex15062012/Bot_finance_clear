from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChannelBroadcast(Base):
    """Одна публикация в канал: слот даты и часа, чтобы не отправить дважды."""

    __tablename__ = "channel_broadcasts"
    __table_args__ = (
        UniqueConstraint(
            "platform_chat_id",
            "slot_key",
            name="uq_channel_broadcasts_chat_slot",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    platform_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    slot_key: Mapped[str] = mapped_column(String(32), nullable=False)
    variant_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
