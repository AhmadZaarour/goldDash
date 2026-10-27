from sqlalchemy import String, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from datetime import datetime

class InventoryService(Base):

    __tablename__ = "inventoryServices"

    id : Mapped[int] = mapped_column(
        primary_key= True,
    )

    notes : Mapped[str] = mapped_column(
        String(200),
        nullable=True,
    )

    customer_id : Mapped[int] = mapped_column(
        ForeignKey("customers.id"),
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

    cost : Mapped[float] = mapped_column(
        float,
    )

    created_at : Mapped[datetime] = mapped_column(
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,

    )