from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConsentDocument(Base):
    """Заготовка под юридические документы (v1: не активировано)."""

    __tablename__ = "consent_documents"
    __table_args__ = (UniqueConstraint("code", "version", name="uq_consent_doc_code_version"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    policy_url: Mapped[str | None] = mapped_column(String(2048))
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)


class Consent(Base):
    """Фиксация согласия пользователя (включается флагом в settings)."""

    __tablename__ = "consents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(nullable=False, index=True)
    consent_type: Mapped[str] = mapped_column(String(100), nullable=False)
    document_version: Mapped[str] = mapped_column(String(32), nullable=False)
    platform_event_id: Mapped[str | None] = mapped_column(String(128))
    consented_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
