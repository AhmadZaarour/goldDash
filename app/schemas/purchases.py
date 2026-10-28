from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class PurchaseLineCreate(BaseModel):
    image_url: HttpUrl | None = Field(default=None, max_length=2048)
    supplier_id: int
    product_id: int
    weight: Decimal = Field(gt=0, decimal_places=3, max_digits=12)
    gold_price_per_gram: Decimal = Field(ge=0, decimal_places=4, max_digits=14)
    gold_charge_in_grams: Decimal = Field(ge=0, decimal_places=3, max_digits=14)
    making_charge: Decimal = Field(ge=0, decimal_places=2, max_digits=14)


class PurchaseCreate(BaseModel):
    supplier_id: int
    invoice_number: str | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=200)
    created_by: int | None = None
    created_at: datetime | None = Field(default_factory=lambda: datetime.now(UTC))
    location_id: int
    items: list[PurchaseLineCreate] = Field(min_length=1)

    @model_validator(mode="after")
    def one_supplier_per_invoice(self):
        if any(line.supplier_id != self.supplier_id for line in self.items):
            raise ValueError("A purchase invoice must have exactly one supplier")
        return self


class PurchaseStockItemCreate(BaseModel):
    making_charge: Decimal = Field(default=0, ge=0, decimal_places=2, max_digits=14)
    product_id: int
    stock_for: Literal["factory", "showroom"]
    weight: Decimal = Field(gt=0, decimal_places=3, max_digits=12)
    cost_per_gram: Decimal = Field(ge=0, decimal_places=4, max_digits=14)


class PurchaseStockCreate(BaseModel):
    supplier_id: int
    invoice_number: str | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=200)
    created_by: int | None = None
    created_at: datetime | None = Field(default_factory=lambda: datetime.now(UTC))
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
    weight: Decimal | None = None
    gold_price_per_gram: Decimal | None = None
    gold_charge_in_grams: Decimal | None = None
    making_charge: Decimal | None = None


class PurchaseStockUpdate(BaseModel):
    purchase_id: int | None = None
    product_id: int | None = None
    stock_for: str | None = Field(default=None, min_length=1, max_length=50)
    weight: Decimal | None = None
    cost_per_gram: Decimal | None = None


class PurchaseStockResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    purchase_id: int
    product_id: int
    stock_for: str
    weight: Decimal
    cost_per_gram: Decimal


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
    weight: Decimal
    gold_price_per_gram: Decimal
    gold_charge_in_grams: Decimal
    making_charge: Decimal
