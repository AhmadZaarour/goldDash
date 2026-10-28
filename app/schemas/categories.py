from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

CategoryName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class CategoryCreate(BaseModel):
    name: CategoryName
    description: str | None = Field(default=None, max_length=200)


class CategoryUpdate(BaseModel):
    name: CategoryName | None = None
    description: str | None = Field(default=None, max_length=200)

    @field_validator("name", mode="before")
    @classmethod
    def name_cannot_be_null(cls, value):
        if value is None:
            raise ValueError("Name cannot be null")
        return value


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
