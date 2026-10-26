from sqlalchemy import ForeignKey, Float
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class SaleStock(Base):

    __tablename__ = "saleStocks"

    id : Mapped[int] = mapped_column(
        primary_key= True,
    )

    sale_id : Mapped[int] = mapped_column(
        ForeignKey("sales.id"),
        nullable = False,
    )

    supplier_id : Mapped[int] = mapped_column(
        ForeignKey("suppliers.id"),
        nullable = False,
    )

    gold_purity_id : Mapped[int] = mapped_column(

        ForeignKey("goldPurities.id")
    )

    weight : Mapped[float] = mapped_column(
        Float,
    )

    gold_charge_in_grams : Mapped[float] = mapped_column(
        Float,
    )

    making_charge : Mapped[float] = mapped_column(
        Float,
    )