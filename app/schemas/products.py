from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.product import InventoryType


class ProductCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    sku: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=200)
    category_id: int = Field(gt=0)
    purity_id: int = Field(gt=0)
    inventory_type: InventoryType


class ProductUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    sku: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=200)
    category_id: int | None = Field(default=None, gt=0)
    purity_id: int | None = Field(default=None, gt=0)
    inventory_type: InventoryType | None = None

    @model_validator(mode="after")
    def nonnullable_fields(self):
        for field in ("sku", "name", "category_id", "purity_id", "inventory_type"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    name: str
    description: str | None
    category_id: int
    purity_id: int
    inventory_type: InventoryType
    created_at: datetime
    updated_at: datetime
