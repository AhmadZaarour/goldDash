from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class InventoryType(StrEnum):
    ITEM = "item"
    BULK = "bulk"


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("inventory_type IN ('item', 'bulk')", name="ck_product_inventory_type"),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    sku: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True,
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(50),
    )

    description: Mapped[str] = mapped_column(
        String(200),
        nullable=True,
    )

    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id"),
        nullable=False,
    )

    purity_id: Mapped[int] = mapped_column(
        ForeignKey("goldPurities.id"),
        nullable=False,
    )

    inventory_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
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
