from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class PriceSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    buy_adjustment_usd: Decimal = Field(decimal_places=2, max_digits=12)
    sell_adjustment_usd: Decimal = Field(decimal_places=2, max_digits=12)


class QuoteModeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manual_ounce_usd: Decimal | None = Field(gt=0, decimal_places=6, max_digits=20)


class PriceSettingsResponse(PriceSettingsUpdate):
    model_config = ConfigDict(from_attributes=True)
    unit: str
    manual_ounce_usd: Decimal | None = None
    quote_updated_at: datetime | None = None
    updated_by: int | None = None
    updated_at: datetime | None = None
