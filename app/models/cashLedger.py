from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CashEntry(Base):
    __tablename__ = "cash_entries"
    __table_args__ = (
        CheckConstraint(
            "(kind = 'sale' AND amount_usd >= 0 AND sale_id IS NOT NULL "
            "AND return_id IS NULL AND supplier_entry_id IS NULL) "
            "OR (kind = 'refund' AND amount_usd <= 0 AND return_id IS NOT NULL "
            "AND sale_id IS NULL AND supplier_entry_id IS NULL) "
            "OR (kind IN ('supplier_sent', 'supplier_received', 'supplier_reversal') "
            "AND supplier_entry_id IS NOT NULL AND sale_id IS NULL AND return_id IS NULL)"
            " OR (kind IN ('expense', 'withdrawal') AND amount_usd < 0 "
            "AND sale_id IS NULL AND return_id IS NULL AND supplier_entry_id IS NULL "
            "AND description IS NOT NULL AND length(trim(description)) > 0)",
            name="ck_cash_sources_outflows",
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True)
    sale_id: Mapped[int | None] = mapped_column(ForeignKey("sales.id"), unique=True)
    return_id: Mapped[int | None] = mapped_column(ForeignKey("item_returns.id"), unique=True)
    supplier_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("supplier_ledger_entries.id"), unique=True
    )
    description: Mapped[str | None] = mapped_column(String(500))
    category: Mapped[str | None] = mapped_column(String(50))
    kind: Mapped[str] = mapped_column(String(20))
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class CashReconciliation(Base):
    __tablename__ = "cash_reconciliations"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(100), unique=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"))
    from_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    to_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    opening_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    expected_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    counted_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    variance_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
