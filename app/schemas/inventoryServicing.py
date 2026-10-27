from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ServiceCreate(BaseModel):
    notes: str | None = Field(default=None, max_length=200)
    customer_id: int
    barcode: str = Field(min_length=1, max_length=50)
    status: str = Field(default="received", min_length=1, max_length=50)
    cost: Decimal = Field(ge=0)
    created_at: datetime | None = Field(default_factory=datetime.utcnow)


class ServiceUpdate(BaseModel):
    notes: str | None = Field(default=None, max_length=200)
    status: str = Field(default="received", min_length=1, max_length=50)
    cost: Decimal = Field(ge=0)


class ServiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    notes: str | None
    customer_id: int
    barcode: str
    status: str
    cost: Decimal = Field(ge=0)
    created_at: datetime
