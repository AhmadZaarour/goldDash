from datetime import UTC, datetime
from decimal import Decimal

from pydantic import AliasPath, BaseModel, ConfigDict, Field, HttpUrl


class InventoryItemCreate(BaseModel):
    image_url: HttpUrl | None = Field(default=None, max_length=2048)
    location_id: int
    purchase_item_id: int
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
    product_id: int = Field(validation_alias=AliasPath("purchase_item", "product_id"))
    product_name: str = Field(validation_alias=AliasPath("purchase_item", "product", "name"))
    sku: str = Field(validation_alias=AliasPath("purchase_item", "product", "sku"))
    purity_id: int = Field(validation_alias=AliasPath("purchase_item", "product", "purity_id"))
    category_id: int = Field(validation_alias=AliasPath("purchase_item", "product", "category_id"))
    weight: Decimal = Field(validation_alias=AliasPath("purchase_item", "weight"))
    base_cost_usd: Decimal
    image_url: str | None = None
    model_config = ConfigDict(from_attributes=True)

    id: int
    location_id: int
    purchase_item_id: int
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
