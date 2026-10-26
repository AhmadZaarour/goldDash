from sqlalchemy import ForeignKey, String, Enum, Float
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class StockFor(str, Enum):
    FACTORY = "factory"
    SHOWROOM = "showroom"

class PurchaseStock(Base):

    __tablename__ = "purchaseStocks"

    id : Mapped[int] = mapped_column(
        primary_key= True,
    )

    purchase_id : Mapped[int] = mapped_column(
        ForeignKey("purchases.id"),
        nullable = False,
    )

    product_id : Mapped[int] = mapped_column(
        ForeignKey ("products.id")
    )

    stock_for : Mapped[StockFor] = mapped_column(
        String,
        nullable = False,
    )

    weight : Mapped[float] = mapped_column(
        Float,
    )

    cost_per_gram : Mapped[float] = mapped_column(
        Float,
    )