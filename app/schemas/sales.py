from datetime import datetime

from pydantic import BaseModel, Field, ConfigDict

class SaleLineCreate(BaseModel):
    inventory_item_id: int
    gold_price_per_gram: float
    discount: float
    sell_price: float

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
    weight: float
    gold_charge_in_grams: float
    making_charge: float

class SaleStockCreate(BaseModel):
    invoice_number: str | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=200)
    created_by: int
    created_at: datetime | None = Field(default_factory=datetime.utcnow)
    location_id: int
    item: SaleStockItemCreate

class SaleStockResponse(BaseModel):
    model_config = ConfigDict(from_attributees=True)

    id: int
    sale_id: int
    supplier_id: int
    gold_purity_id: int
    weight: float
    gold_charge_in_grams: float
    making_charge: float

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
    gold_price_per_gram: float
    discount: float
    sell_price: float