"""Production provenance and paired business operations."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.workspace import UnitOwned


class OperationDocument(Base):
    __tablename__ = "business_operations"
    __table_args__ = (
        Index(
            "uq_workspace_opening",
            "unit",
            "location_id",
            unique=True,
            postgresql_where=text("kind = 'opening'"),
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    unit: Mapped[str] = mapped_column(String(20), index=True)
    other_unit: Mapped[str | None] = mapped_column(String(20))
    kind: Mapped[str] = mapped_column(String(30), index=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    other_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    note: Mapped[str] = mapped_column(String(500))
    reversal_of_id: Mapped[int | None] = mapped_column(
        ForeignKey("business_operations.id"), unique=True
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProductionBatch(UnitOwned, Base):
    __tablename__ = "production_batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active")
    reference: Mapped[str | None] = mapped_column(String(100))
    note: Mapped[str | None] = mapped_column(String(500))
    material_cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    direct_cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    total_cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    input_gold_24k: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    output_gold_24k: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    scrap_gold_24k: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    loss_gold_24k: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    details: Mapped[dict] = mapped_column(JSON)
    operation_id: Mapped[int] = mapped_column(ForeignKey("business_operations.id"))
    gold_quote_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProductionPiece(Base):
    __tablename__ = "production_pieces"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("production_batches.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    product: Mapped["Product"] = relationship(lazy="joined")
    weight: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    valuation_factor: Mapped[Decimal] = mapped_column(Numeric(14, 10))
    gold_charge_24k: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    gold_price_per_gram: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    making_charge: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    total_cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 4))

    @property
    def gold_charge_in_grams(self):
        return self.weight


class InternalInvoice(Base):
    __tablename__ = "internal_invoices"
    id: Mapped[int] = mapped_column(primary_key=True)
    factory_location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    showroom_location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    gold_24k: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    making_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    gold_price_usd: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    total_value_usd: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    factory_cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    note: Mapped[str | None] = mapped_column(String(500))
    reversal_of_id: Mapped[int | None] = mapped_column(
        ForeignKey("internal_invoices.id"), unique=True
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class InternalInvoiceLine(Base):
    __tablename__ = "internal_invoice_lines"
    __table_args__ = (
        UniqueConstraint("invoice_id", "inventory_item_id", name="uq_internal_invoice_piece"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("internal_invoices.id"), index=True)
    inventory_item_id: Mapped[int] = mapped_column(ForeignKey("inventoryItems.id"))
    gold_24k: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    making_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    factory_cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    showroom_cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 4))


class InternalPayment(Base):
    __tablename__ = "internal_payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    operation_id: Mapped[int] = mapped_column(ForeignKey("business_operations.id"), unique=True)
    direction: Mapped[str] = mapped_column(String(20))
    gold_24k: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    making_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    physical_purity_id: Mapped[int | None] = mapped_column(ForeignKey("goldPurities.id"))
    physical_gold_grams: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    cash_gold_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    gold_price_usd: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    repayment_factor: Mapped[Decimal] = mapped_column(Numeric(14, 10))
    stock_value_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    reversal_of_id: Mapped[int | None] = mapped_column(
        ForeignKey("internal_payments.id"), unique=True
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


if TYPE_CHECKING:
    from app.models.product import Product
