from sqlalchemy import ForeignKey, Float
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class SaleItem(Base):

    __tablename__ = "saleItems"

    id : Mapped[int] = mapped_column(
        primary_key= True,
    )

    sale_id : Mapped[int] = mapped_column(
        ForeignKey("sales.id"),
        nullable = False,
    )

    inventory_item_id : Mapped[int] = mapped_column(
        ForeignKey ("inventoryItems.id")
    )

    gold_price_per_gram : Mapped[float] = mapped_column(
        Float,
    )

    discount : Mapped[float] = mapped_column(
        Float,
    )

    sell_price : Mapped[float] = mapped_column(
        Float,
    )

