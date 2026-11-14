from datetime import UTC, datetime
from decimal import Decimal

from pydantic import AliasPath, BaseModel, ConfigDict, Field, HttpUrl


class InventoryItemCreate(BaseModel):
    image_url: HttpUrl | None = Field(default=None, max_length=2048)
    location_id: int
    purchase_item_id: int | None = None
    production_piece_id: int | None = None
    status: str


class InventoryStockCreate(BaseModel):
    purchase_stock_id: int


class InventoryMovementCreate(BaseModel):
    from_location_id: int | None = None
    to_location_id: int | None = None
    created_by: int | None = None
    sale_id: int | None = None
    inventory_item_id: int
    movement_type: str
    created_at: datetime | None = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime | None = Field(default_factory=lambda: datetime.now(UTC))


class InventoryItemUpdate(BaseModel):
    image_url: HttpUrl | None = Field(default=None, max_length=2048)
    status: str | None = Field(default=None, min_length=1, max_length=50)


class InventoryStockUpdate(BaseModel):
    purchase_stock_id: int


class InventoryMovementUpdate(BaseModel):
    movement_type: str | None = Field(default=None, min_length=1, max_length=50)


class InventoryItemImageUpdate(BaseModel):
    image_url: HttpUrl | None = Field(max_length=2048)


class InventoryItemResponse(BaseModel):
    gold_charge_24k: Decimal | None = Field(
        default=None, validation_alias=AliasPath("origin_line", "gold_charge_24k")
    )
    product_id: int = Field(validation_alias=AliasPath("origin_line", "product_id"))
    product_name: str = Field(validation_alias=AliasPath("origin_line", "product", "name"))
    sku: str = Field(validation_alias=AliasPath("origin_line", "product", "sku"))
    purity_id: int = Field(validation_alias=AliasPath("origin_line", "product", "purity_id"))
    category_id: int = Field(validation_alias=AliasPath("origin_line", "product", "category_id"))
    weight: Decimal = Field(validation_alias=AliasPath("origin_line", "weight"))
    base_cost_usd: Decimal
    image_url: str | None = None
    model_config = ConfigDict(from_attributes=True)

    id: int
    location_id: int
    purchase_item_id: int | None
    production_piece_id: int | None = None
    unit: str | None = None
    barcode: str | None = Field(default=None, min_length=1, max_length=50)
    status: str | None = Field(default=None, min_length=1, max_length=50)


class InventoryStockResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    purchase_stock_id: int


class InventoryMovementResponse(BaseModel):
    from_location_id: int | None = None
    to_location_id: int | None = None
    created_by: int | None = None
    sale_id: int | None = None
    model_config = ConfigDict(from_attributes=True)

    id: int
    inventory_item_id: int
    movement_type: str | None = Field(default=None, min_length=1, max_length=50)
    created_at: datetime
    updated_at: datetime
