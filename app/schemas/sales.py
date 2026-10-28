from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class SaleLineCreate(BaseModel):
    inventory_item_id: int
    gold_price_per_gram: Decimal = Field(ge=0, decimal_places=4, max_digits=14)
    discount: Decimal = Field(ge=0, decimal_places=2, max_digits=14)
    sell_price: Decimal = Field(ge=0, decimal_places=2, max_digits=14)


class SaleCreate(BaseModel):
    customer_id: int | None = None
    invoice_number: str | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=200)
    created_by: int | None = None
    created_at: datetime | None = Field(default_factory=lambda: datetime.now(UTC))
    location_id: int
    items: list[SaleLineCreate] = Field(min_length=1)


class SaleStockItemCreate(BaseModel):
    supplier_id: int
    gold_purity_id: int
    weight: Decimal = Field(gt=0, decimal_places=3, max_digits=12)
    gold_charge_in_grams: Decimal = Field(ge=0, decimal_places=3, max_digits=14)
    making_charge: Decimal = Field(ge=0, decimal_places=2, max_digits=14)


class SaleStockCreate(BaseModel):
    invoice_number: str | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=200)
    created_by: int | None = None
    created_at: datetime | None = Field(default_factory=lambda: datetime.now(UTC))
    location_id: int
    item: SaleStockItemCreate


class SaleStockResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sale_id: int
    supplier_id: int
    gold_purity_id: int
    weight: Decimal = Field(gt=0, decimal_places=3, max_digits=12)
    gold_charge_in_grams: Decimal = Field(ge=0, decimal_places=3, max_digits=14)
    making_charge: Decimal = Field(ge=0, decimal_places=2, max_digits=14)


class SaleResponse(BaseModel):
    customer_id: int | None = None
    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_number: str | None
    notes: str | None
    created_by: int
    created_at: datetime
    location_id: int


class SaleItemResponse(BaseModel):
    returned: bool
    return_id: int | None
    refund_usd: Decimal
    returned_at: datetime | None
    model_config = ConfigDict(from_attributes=True)

    id: int
    sale_id: int
    inventory_item_id: int
    gold_price_per_gram: Decimal = Field(ge=0, decimal_places=4, max_digits=14)
    discount: Decimal = Field(ge=0, decimal_places=2, max_digits=14)
    sell_price: Decimal
