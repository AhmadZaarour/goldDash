from pydantic import BaseModel, Field
from decimal import Decimal
from typing import Literal

class ItemTransfer(BaseModel):
    location_id: int


class ItemReturnCreate(BaseModel):
    sale_item_id: int
    location_id: int
    refund_usd: Decimal = Field(ge=0, max_digits=14, decimal_places=2)


class StockTransfer(BaseModel):
    purity_id: int
    source_location_id: int
    source_placement: Literal["factory", "showroom"]
    destination_location_id: int
    destination_placement: Literal["factory", "showroom"]
    weight: Decimal = Field(gt=0, max_digits=12, decimal_places=3)

class StockTransferResponse(BaseModel):
    id: int
    source_weight: Decimal
    destination_weight: Decimal