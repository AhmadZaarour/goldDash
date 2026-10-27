from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ItemReturn(Base):
    __tablename__ = "item_returns"
    __table_args__ = (CheckConstraint("refund_usd >= 0", name="ck_return_refund"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_item_id: Mapped[int] = mapped_column(ForeignKey("saleItems.id"), unique=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    refund_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
