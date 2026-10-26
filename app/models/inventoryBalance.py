from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Enum,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

class StockFor(str, Enum):
    FACTORY = "factory"
    SHOWROOM = "showroom"

class InventoryBalance(Base):
    __tablename__ = "inventory_balances"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True
    )
    purity_id: Mapped[int] = mapped_column(
        ForeignKey("goldPurities.id"), nullable=False
    )
    location_id: Mapped[int] = mapped_column(
        ForeignKey("locations.id"), nullable=False
    )
    placement: Mapped[StockFor] = mapped_column(
        String,
        nullable = False,
    )
    total_weight: Mapped[float] = mapped_column(
        Numeric(12, 3), nullable=False, default=0
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )