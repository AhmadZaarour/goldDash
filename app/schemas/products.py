from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProductCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=200)
    category_id: int
    purity_id: int
    inventory_type: str = Field(min_length=1, max_length=50)


class ProductUpdate(BaseModel):
    sku: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=200)
    category_id: int | None = None
    purity_id: int | None = None
    inventory_type: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
    )


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    name: str
    description: str | None
    category_id: int
    purity_id: int
    inventory_type: str
    created_at: datetime
    updated_at: datetime