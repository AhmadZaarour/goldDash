from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

ServiceStatus = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)
]


class ServiceCreate(BaseModel):
    notes: str | None = Field(default=None, max_length=200)
    customer_id: int
    barcode: str = Field(min_length=1, max_length=50)
    status: ServiceStatus = "received"
    cost: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    created_at: datetime | None = Field(default_factory=lambda: datetime.now(UTC))


class ServiceUpdate(BaseModel):
    notes: str | None = Field(default=None, max_length=200)
    status: ServiceStatus | None = None
    cost: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)

    @field_validator("status", "cost", mode="before")
    @classmethod
    def nonnullable_fields(cls, value):
        if value is None:
            raise ValueError("This field cannot be null")
        return value


class ServiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    notes: str | None
    customer_id: int
    barcode: str
    status: str
    cost: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    created_at: datetime
