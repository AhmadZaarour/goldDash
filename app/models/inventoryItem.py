from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class InventoryItem(Base):

    __tablename__ = "inventoryItems"

    id : Mapped[int] = mapped_column(
        primary_key= True,
    )

    purchase_item_id : Mapped[int] = mapped_column(
        ForeignKey ("purchaseItems.id")
    )

    barcode : Mapped[str] = mapped_column(
        String(50),
        unique = True,
        index = True,
        nullable = False,
    )

    status : Mapped[str] = mapped_column(
        String(50),
    )
