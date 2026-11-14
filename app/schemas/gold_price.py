from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class PriceSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    buy_adjustment_usd: Decimal = Field(decimal_places=2, max_digits=12)
    sell_adjustment_usd: Decimal = Field(decimal_places=2, max_digits=12)


class PriceSettingsResponse(PriceSettingsUpdate):
    model_config = ConfigDict(from_attributes=True)
    unit: str
    updated_by: int | None = None
    updated_at: datetime | None = None
