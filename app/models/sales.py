from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Sale(Base):
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

    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))

    location_id: Mapped[int] = mapped_column(
        ForeignKey("locations.id"),
    )
