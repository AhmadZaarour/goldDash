from decimal import Decimal

from sqlalchemy import Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class GoldPurity(Base):
    __tablename__ = "goldPurities"

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    name: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True,
        nullable=False,
    )

    karat: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    repayment_factor: Mapped[Decimal] = mapped_column(
        Numeric(10, 6),
        nullable=False,
        default=lambda ctx: {18: Decimal("0.74"), 21: Decimal("0.865"), 24: Decimal(1)}.get(
            ctx.get_current_parameters()["karat"],
            Decimal(str(ctx.get_current_parameters()["purity"])) / 100,
        ),
    )

    purity: Mapped[Decimal] = mapped_column(
        Numeric(10, 6),
        nullable=False,
    )
