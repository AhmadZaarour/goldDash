from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class InventoryBalanceCreate(BaseModel):
    purity_id: int
    location_id: int
    placement: str = Field(min_length=1, max_length=50)
    total_weight: Decimal = Field(default=0)
    updated_at: datetime | None = Field(default_factory=lambda: datetime.now(UTC))


class InventoryBalanceUpdate(BaseModel):
    purity_id: int | None = None
    location_id: int | None = None
    placement: str | None = Field(default=None, min_length=1, max_length=50)
    total_weight: Decimal | None = None
    updated_at: datetime | None = Field(default_factory=lambda: datetime.now(UTC))


class InventoryBalanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    purity_id: int
    location_id: int
    placement: str
    total_weight: Decimal
    updated_at: datetime
