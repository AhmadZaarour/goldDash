from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SaleBook(Base):
    __tablename__ = "saleBook"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"))

    recieved_gold_charge: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
    )

    recieved_making_charge: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
