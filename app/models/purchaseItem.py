from sqlalchemy import ForeignKey, Float
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class PurchaseItem(Base):

    __tablename__ = "purchaseItems"

    id : Mapped[int] = mapped_column(
        primary_key= True,
    )

    supplier_id : Mapped[int] = mapped_column(
        ForeignKey("suppliers.id"),
        nullable = False,
    )

    purchase_id : Mapped[int] = mapped_column(
        ForeignKey("purchases.id"),
        nullable = False,
    )

    product_id : Mapped[int] = mapped_column(
        ForeignKey ("products.id")
    )

    weight : Mapped[float] = mapped_column(
        Float,
    )

    gold_price_per_gram : Mapped[float] = mapped_column(
        Float,
    )

    gold_charge_in_grams : Mapped[float] = mapped_column(
        Float,
    )

    making_charge : Mapped[float] = mapped_column(
        Float,
    )

