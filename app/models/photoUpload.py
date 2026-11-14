"""Temporary purchase photos, claimed atomically by the purchase transaction."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.workspace import UnitOwned


class PhotoUpload(UnitOwned, Base):
    __tablename__ = "purchase_photo_uploads"
    token: Mapped[str] = mapped_column(String(32), primary_key=True)
    filename: Mapped[str] = mapped_column(String(36), unique=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    inventory_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("inventoryItems.id"), unique=True
    )
