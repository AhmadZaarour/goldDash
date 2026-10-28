from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator

CustomerName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
CustomerPhone = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)
]


class CustomerCreate(BaseModel):
    name: CustomerName
    phone: CustomerPhone | None = None


class CustomerUpdate(BaseModel):
    name: CustomerName | None = None
    phone: CustomerPhone | None = None

    @field_validator("name", mode="before")
    @classmethod
    def name_cannot_be_null(cls, value):
        if value is None:
            raise ValueError("Name cannot be null")
        return value


class CustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: str | None
    created_at: datetime
