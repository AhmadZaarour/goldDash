from sqlalchemy import ForeignKey, Float, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from datetime import datetime

class SaleBook(Base):

    __tablename__ = "saleBook"

    id : Mapped[int] = mapped_column(
        primary_key = True,
    )

    sale_id : Mapped[int] = mapped_column(
        ForeignKey ("sales.id")
    )

    recieved_gold_charge : Mapped[float] = mapped_column(
        Float,
    )

    recieved_making_charge : Mapped[float] = mapped_column(
        Float,
    )

    updated_at : Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )