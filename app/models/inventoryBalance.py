from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StockFor(StrEnum):
    FACTORY = "factory"
    SHOWROOM = "showroom"


class InventoryBalance(Base):
    __tablename__ = "inventory_balances"
    __table_args__ = (
        UniqueConstraint("purity_id", "location_id", "placement", name="uq_balance_bucket"),
        CheckConstraint("total_weight >= 0", name="ck_balance_nonnegative"),
        CheckConstraint("placement IN ('factory', 'showroom')", name="ck_balance_placement"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    purity_id: Mapped[int] = mapped_column(ForeignKey("goldPurities.id"), nullable=False)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    placement: Mapped[StockFor] = mapped_column(
        String,
        nullable=False,
    )
    total_weight: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
