from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

ServiceStatus = Literal["in_progress", "finished"]
Barcode = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class ServiceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notes: str | None = Field(default=None, max_length=200)
    status: ServiceStatus = "in_progress"


class ServiceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notes: str | None = Field(default=None, max_length=200)
    status: ServiceStatus | None = None

    @field_validator("status", mode="before")
    @classmethod
    def nonnullable_status(cls, value):
        if value is None:
            raise ValueError("This field cannot be null")
        return value


class ServiceSaleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    barcode: Barcode
    location_id: int = Field(gt=0)
    cost: Decimal = Field(ge=0, max_digits=14, decimal_places=2)


class ServiceSaleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    service_id: int
    barcode: str
    notes: str | None
    location_id: int
    amount_usd: Decimal
    created_by: int
    created_at: datetime
    unit: str | None


class ServiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    notes: str | None
    customer_id: int | None
    barcode: str
    status: str
    legacy_status: str | None = None
    # Legacy intake estimates are preserved, but never counted as collected money.
    cost: Decimal
    created_at: datetime
    sale: ServiceSaleResponse | None = None
