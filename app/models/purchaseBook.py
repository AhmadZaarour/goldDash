from sqlalchemy import ForeignKey, Float, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from datetime import datetime

class PurchaseBook(Base):

    __tablename__ = "purchaseBook"

    id : Mapped[int] = mapped_column(
        primary_key = True,
    )

    purchase_id : Mapped[int] = mapped_column(
        ForeignKey ("purchases.id")
    )

    paid_gold_charge : Mapped[float] = mapped_column(
        Float,
    )

    paid_making_charge : Mapped[float] = mapped_column(
        Float,
    )

    updated_at : Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )