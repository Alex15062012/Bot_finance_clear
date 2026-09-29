from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserMaterialDelivery(Base):
    """Какой материал уже отправлен пользователю и в каком сообщении MAX."""

    __tablename__ = "user_material_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "material_id",
            name="uq_user_material_deliveries_user_material",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    material_id: Mapped[int] = mapped_column(
        ForeignKey("materials.id"), nullable=False, index=True
    )
    message_mid: Mapped[str | None] = mapped_column(String(128))
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
