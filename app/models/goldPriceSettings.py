"""Each workspace owns its gold quote settings and customer ounce adjustments."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.workspace import UnitOwned


class GoldPriceSettings(UnitOwned, Base):
    __tablename__ = "gold_price_settings"
    __table_args__ = (
        CheckConstraint("unit IN ('factory', 'showroom')", name="ck_gold_price_unit"),
        CheckConstraint("manual_ounce_usd > 0", name="ck_gold_price_manual_ounce_positive"),
    )
    unit: Mapped[str] = mapped_column(String(20), primary_key=True)
    buy_adjustment_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=0, server_default="0"
    )
    sell_adjustment_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=0, server_default="0"
    )
    manual_ounce_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    quote_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CustomerPriceSnapshot:
    market_ounce_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    ounce_adjustment_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    applied_ounce_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
