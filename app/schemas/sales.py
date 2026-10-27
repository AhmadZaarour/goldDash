from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class SaleLineCreate(BaseModel):
    inventory_item_id: int
    gold_price_per_gram: Decimal = Field(ge=0)
    discount: Decimal = Field(ge=0)
    sell_price: Decimal = Field(ge=0)


class SaleCreate(BaseModel):
    invoice_number: str | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=200)
    created_by: int
    created_at: datetime | None = Field(default_factory=datetime.utcnow)
    location_id: int
    items: list[SaleLineCreate] = Field(min_length=1)


class SaleStockItemCreate(BaseModel):
    supplier_id: int
    gold_purity_id: int
    weight: Decimal = Field(gt=0)
    gold_charge_in_grams: Decimal = Field(ge=0)
    making_charge: Decimal = Field(ge=0)


class SaleStockCreate(BaseModel):
    invoice_number: str | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=200)
    created_by: int
    created_at: datetime | None = Field(default_factory=datetime.utcnow)
    location_id: int
    item: SaleStockItemCreate


class SaleStockResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sale_id: int
    supplier_id: int
    gold_purity_id: int
    weight: float = Field(gt=0)
    gold_charge_in_grams: float = Field(ge=0)
    making_charge: float = Field(ge=0)


class SaleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_number: str | None
    notes: str | None
    created_by: int
    created_at: datetime
    location_id: int


class SaleItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sale_id: int
    inventory_item_id: int
    gold_price_per_gram: float = Field(ge=0)
    discount: float = Field(ge=0)
    sell_price: float
