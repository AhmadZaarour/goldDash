from decimal import Decimal
from enum import StrEnum

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StockFor(StrEnum):
    FACTORY = "factory"
    SHOWROOM = "showroom"


class PurchaseStock(Base):
    __tablename__ = "purchaseStocks"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    purchase_id: Mapped[int] = mapped_column(
        ForeignKey("purchases.id"),
        nullable=False,
    )

    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))

    stock_for: Mapped[StockFor] = mapped_column(
        String,
        nullable=False,
    )

    weight: Mapped[Decimal] = mapped_column(
        Numeric(14, 3),
    )

    cost_per_gram: Mapped[Decimal] = mapped_column(
        Numeric(14, 4),
    )
