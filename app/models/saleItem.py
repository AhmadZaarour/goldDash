from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SaleItem(Base):
    __tablename__ = "saleItems"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    sale_id: Mapped[int] = mapped_column(
        ForeignKey("sales.id"),
        nullable=False,
    )

    inventory_item_id: Mapped[int] = mapped_column(ForeignKey("inventoryItems.id"))

    gold_price_per_gram: Mapped[Decimal] = mapped_column(
        Numeric(14, 4),
    )

    discount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
    )

    sell_price: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
    )
