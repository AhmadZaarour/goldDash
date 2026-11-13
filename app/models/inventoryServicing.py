from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.workspace import UnitOwned


class InventoryService(UnitOwned, Base):
    __tablename__ = "inventoryServices"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    notes: Mapped[str] = mapped_column(
        String(200),
        nullable=True,
    )

    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id"),
    )

    barcode: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(50),
    )

    legacy_status: Mapped[str | None] = mapped_column(String(50))

    cost: Mapped[Decimal] = mapped_column(
        Numeric(14, 2),
        default=Decimal("0"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    sale: Mapped["ServiceSale | None"] = relationship(lazy="selectin", uselist=False)


class ServiceSale(UnitOwned, Base):
    __tablename__ = "service_sales"
    __table_args__ = (CheckConstraint("amount_usd >= 0", name="ck_service_sale_amount"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("inventoryServices.id"), unique=True)
    barcode: Mapped[str] = mapped_column(String(50))
    notes: Mapped[str | None] = mapped_column(String(200))
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True)
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
