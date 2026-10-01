from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ChannelSchedule(Base):
    """Когда публиковать в каналы приглашение задать финансовый вопрос."""

    __tablename__ = "channel_schedules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="daily")
    weekday: Mapped[int | None] = mapped_column(Integer)
    on_date: Mapped[str | None] = mapped_column(String(10))
    send_time: Mapped[str] = mapped_column(String(5), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
