from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class InventoryMovement(Base):
    __tablename__ = "inventoryMovements"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    inventory_item_id: Mapped[int] = mapped_column(
        ForeignKey("inventoryItems.id"),
        nullable=False,
    )

    from_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))
    to_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    sale_id: Mapped[int | None] = mapped_column(ForeignKey("sales.id"))

    movement_type: Mapped[str] = mapped_column(
        String(50),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
