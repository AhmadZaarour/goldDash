"""Signed supplier obligations: positive means the shop owes the supplier."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SupplierLedgerEntry(Base):
    __tablename__ = "supplier_ledger_entries"
    __table_args__ = (
        CheckConstraint("gold_grams = 0 OR purity_id IS NOT NULL", name="ck_ledger_gold_purity"),
        CheckConstraint("gold_grams != 0 OR making_usd != 0", name="ck_ledger_nonzero"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    purity_id: Mapped[int | None] = mapped_column(ForeignKey("goldPurities.id"))
    purchase_id: Mapped[int | None] = mapped_column(ForeignKey("purchases.id"))
    sale_id: Mapped[int | None] = mapped_column(ForeignKey("sales.id"))
    source_key: Mapped[str] = mapped_column(String(160), unique=True)
    reversal_of_id: Mapped[int | None] = mapped_column(
        ForeignKey("supplier_ledger_entries.id"), unique=True
    )
    note: Mapped[str | None] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(30))
    gold_grams: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    making_usd: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
