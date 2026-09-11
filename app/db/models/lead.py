from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LeadStatus(StrEnum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    MEETING_OFFERED = "meeting_offered"
    MEETING_SCHEDULED = "meeting_scheduled"
    COMPLETED = "completed"
    POSTPONED = "postponed"


LEAD_STATUS_LABELS = {
    LeadStatus.NEW: "Новая заявка",
    LeadStatus.IN_PROGRESS: "В работе",
    LeadStatus.MEETING_OFFERED: "Встреча предложена",
    LeadStatus.MEETING_SCHEDULED: "Встреча назначена",
    LeadStatus.COMPLETED: "Завершена",
    LeadStatus.POSTPONED: "Отложена",
}


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(64), default=LeadStatus.NEW.value)
    source: Mapped[str | None] = mapped_column(String(100))
    assigned_to: Mapped[str | None] = mapped_column(String(255))
    comment: Mapped[str | None] = mapped_column(Text)
    platform_message_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
