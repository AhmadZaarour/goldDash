from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.workspace import UnitOwned


class InventoryStock(UnitOwned, Base):
    __tablename__ = "inventoryStocks"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    purchase_stock_id: Mapped[int] = mapped_column(ForeignKey("purchaseStocks.id"), unique=True)
