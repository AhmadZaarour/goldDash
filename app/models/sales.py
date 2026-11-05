from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.workspace import UnitOwned


class Sale(UnitOwned, Base):
    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    invoice_number: Mapped[str] = mapped_column(
        String(50),
        nullable=True,
    )

    notes: Mapped[str] = mapped_column(
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

    gold_quote_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    kind: Mapped[str] = mapped_column(
        String(20), nullable=False, default="customer", server_default="customer"
    )
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"))

    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))

    location_id: Mapped[int] = mapped_column(
        ForeignKey("locations.id"),
    )
