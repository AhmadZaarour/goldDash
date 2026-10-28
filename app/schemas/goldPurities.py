from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

PurityName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class GoldPurityCreate(BaseModel):
    name: PurityName
    karat: int = Field(ge=1, le=24)
    purity: float = Field(gt=0, le=100, allow_inf_nan=False)


class GoldPurityUpdate(BaseModel):
    name: PurityName | None = None
    karat: int | None = Field(default=None, ge=1, le=24)
    purity: float | None = Field(default=None, gt=0, le=100, allow_inf_nan=False)

    @field_validator("name", "karat", "purity", mode="before")
    @classmethod
    def nonnullable_fields(cls, value):
        if value is None:
            raise ValueError("This field cannot be null")
        return value


class GoldPurityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    karat: int
    purity: float
