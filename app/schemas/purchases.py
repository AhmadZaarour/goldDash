from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PurchaseLineCreate(BaseModel):
    supplier_id: int
    product_id: int
    weight: float = Field(gt=0)
    gold_price_per_gram: float = Field(ge=0)
    gold_charge_in_grams: float = Field(ge=0)
    making_charge: float = Field(ge=0)
    barcode: str = Field(min_length=1, max_length=50)

class PurchaseCreate(BaseModel):
    invoice_number: str | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=200)
    created_by: int
    created_at: datetime | None = Field(default_factory=datetime.utcnow)
    location_id: int
    items: list[PurchaseLineCreate] = Field(min_length=1)

class PurchaseStockItemCreate(BaseModel):
    product_id: int
    stock_for: str = Field(min_length=1, max_length=50)
    weight: float = Field(gt=0)
    cost_per_gram: float = Field(ge=0)

class PurchaseStockCreate(BaseModel):
    invoice_number: str | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=200)
    created_by: int
    created_at: datetime | None = Field(default_factory=datetime.utcnow)
    location_id: int
    item: PurchaseStockItemCreate

class PurchaseUpdate(BaseModel):
    invoice_number: str | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=200)
    location_id: int | None = None

class PurchaseItemUpdate(BaseModel):
    supplier_id: int | None = None
    purchase_id: int | None = None
    product_id: int | None = None
    weight: float | None = None
    gold_price_per_gram: float | None = None
    gold_charge_in_grams: float | None = None
    making_charge: float | None = None

class PurchaseStockUpdate(BaseModel):
    purchase_id: int | None = None
    product_id: int | None = None
    stock_for: str | None = Field(default=None, min_length=1, max_length=50)
    weight: float | None = None
    cost_per_gram: float | None = None

class PurchaseStockResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    purchase_id: int
    product_id: int
    stock_for: str
    weight: float
    cost_per_gram: float

class PurchaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_number: str | None
    notes: str | None
    created_by: int
    created_at: datetime
    location_id: int

class PurchaseItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    supplier_id: int
    purchase_id: int
    product_id: int
    weight: float
    gold_price_per_gram: float
    gold_charge_in_grams: float
    making_charge: float