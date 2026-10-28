from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator

LocationName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
LocationCode = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
LocationAddress = Annotated[str, StringConstraints(max_length=200)]


class LocationCreate(BaseModel):
    name: LocationName
    code: LocationCode
    address: LocationAddress | None = None
    is_active: bool = True


class LocationUpdate(BaseModel):
    name: LocationName | None = None
    code: LocationCode | None = None
    address: LocationAddress | None = None
    is_active: bool | None = None

    @field_validator("name", "code", "is_active", mode="before")
    @classmethod
    def nonnullable_fields(cls, value):
        if value is None:
            raise ValueError("This field cannot be null")
        return value


class LocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str
    address: str | None
    is_active: bool
