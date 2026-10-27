from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PurchaseBook(Base):
    __tablename__ = "purchaseBook"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    purchase_id: Mapped[int] = mapped_column(ForeignKey("purchases.id"))

    paid_gold_charge: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
    )

    paid_making_charge: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
