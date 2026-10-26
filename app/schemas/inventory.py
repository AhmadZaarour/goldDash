from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime

class InventoryItemCreate(BaseModel):
    purchase_item_id: int
    barcode: str
    status: str

class InventoryStockCreate(BaseModel):
    purchase_stock_id: int

class InventoryMovementCreate(BaseModel):
    inventory_item_id: int
    movement_type: str
    created_at: datetime | None = Field(default_factory=datetime.utcnow)
    updated_at: datetime | None = Field(default_factory=datetime.utcnow)

class InventoryItemUpdate(BaseModel):
    barcode: str | None = Field(default=None, min_length=1, max_length=50)
    status: str | None = Field(default=None, min_length=1, max_length=50)

class InventoryStockUpdate(BaseModel):
    purchase_stock_id: int

class InventoryMovementUpdate(BaseModel):
    movement_type: str | None = Field(default=None, min_length=1, max_length=50)

class InventoryItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    purchase_item_id:int
    barcode: str | None = Field(default=None, min_length=1, max_length=50)
    status: str | None = Field(default=None, min_length=1, max_length=50)

class InventoryStockResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    purchase_stock_id: int

class InventoryMovementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    inventory_item_id: int
    movement_type: str | None = Field(default=None, min_length=1, max_length=50)
    created_at: datetime
    updated_at: datetime