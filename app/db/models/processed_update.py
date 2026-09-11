from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProcessedUpdate(Base):
    """Идемпотентность: одно событие MAX обрабатывается один раз."""

    __tablename__ = "processed_updates"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_processed_updates_dedupe"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    update_type: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
