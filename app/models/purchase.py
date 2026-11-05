from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.workspace import UnitOwned


class Purchase(UnitOwned, Base):
    __tablename__ = "purchases"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    invoice_number: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default="supplier")
    total_gold_charge_grams: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    gold_debt_24k: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    gold_quote_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_usd: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))

    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"))

    location_id: Mapped[int] = mapped_column(
        ForeignKey("locations.id"),
    )
