from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator

SupplierName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
SupplierPhone = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)
]


class SupplierCreate(BaseModel):
    name: SupplierName
    phone: SupplierPhone
    is_active: bool = True


class SupplierUpdate(BaseModel):
    name: SupplierName | None = None
    phone: SupplierPhone | None = None
    is_active: bool | None = None

    @field_validator("name", "phone", "is_active", mode="before")
    @classmethod
    def nonnullable_fields(cls, value):
        if value is None:
            raise ValueError("This field cannot be null")
        return value


class SupplierResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: str
    is_active: bool
    created_at: datetime
