"""Weight-owned finished stock and purity lines on factory invoices."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.workspace import UnitOwned


class FinishedGoldLot(UnitOwned, Base):
    __tablename__ = "finished_gold_lots"
    __table_args__ = (
        CheckConstraint(
            "weight > 0 AND remaining_weight >= 0 AND remaining_weight <= weight",
            name="ck_finished_weights",
        ),
        CheckConstraint(
            "remaining_cost_usd >= 0 AND remaining_company_cost_usd >= 0", name="ck_finished_values"
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True)
    purity_id: Mapped[int] = mapped_column(ForeignKey("goldPurities.id"), index=True)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("production_batches.id"), index=True)
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("internal_invoices.id"), index=True)
    legacy_item_id: Mapped[int | None] = mapped_column(ForeignKey("inventoryItems.id"), unique=True)
    operation_id: Mapped[int | None] = mapped_column(ForeignKey("business_operations.id"))
    weight: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    remaining_weight: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    company_cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    remaining_cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    remaining_company_cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    valuation_factor: Mapped[Decimal] = mapped_column(Numeric(14, 10))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FactoryWeightLine(Base):
    __tablename__ = "factory_weight_lines"
    __table_args__ = (
        CheckConstraint(
            "(sale_id IS NOT NULL AND invoice_id IS NULL) OR "
            "(sale_id IS NULL AND invoice_id IS NOT NULL)",
            name="ck_weight_trade_source",
        ),
        CheckConstraint(
            "weight > 0 AND making_per_gram >= 0 AND making_usd >= 0",
            name="ck_weight_trade_amounts",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int | None] = mapped_column(ForeignKey("sales.id"), index=True)
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("internal_invoices.id"), index=True)
    purity_id: Mapped[int] = mapped_column(ForeignKey("goldPurities.id"))
    weight: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    gold_24k: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    valuation_factor: Mapped[Decimal] = mapped_column(Numeric(14, 10))
    making_per_gram: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    making_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    gold_price_usd: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    total_value_usd: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    company_cost_usd: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    allocations: Mapped[list] = mapped_column(JSON)
