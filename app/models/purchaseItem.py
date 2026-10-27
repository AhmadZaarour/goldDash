from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PurchaseItem(Base):
    __tablename__ = "purchaseItems"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    supplier_id: Mapped[int] = mapped_column(
        ForeignKey("suppliers.id"),
        nullable=False,
    )

    purchase_id: Mapped[int] = mapped_column(
        ForeignKey("purchases.id"),
        nullable=False,
    )

    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))

    weight: Mapped[Decimal] = mapped_column(
        Numeric(14, 3),
    )

    gold_price_per_gram: Mapped[Decimal] = mapped_column(
        Numeric(14, 4),
    )

    gold_charge_in_grams: Mapped[Decimal] = mapped_column(
        Numeric(14, 3),
    )

    making_charge: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
    )
