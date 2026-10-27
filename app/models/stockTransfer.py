from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StockTransferRecord(Base):
    __tablename__ = "stock_transfers"
    __table_args__ = (CheckConstraint("weight > 0", name="ck_transfer_weight"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    purity_id: Mapped[int] = mapped_column(ForeignKey("goldPurities.id"))
    source_location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    source_placement: Mapped[str] = mapped_column(String(20))
    destination_location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    destination_placement: Mapped[str] = mapped_column(String(20))
    weight: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
