from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class ItemReturnResponse(BaseModel):
    id: int
    sale_item_id: int
    sale_id: int
    inventory_item_id: int
    location_id: int
    refund_usd: Decimal
    created_by: int
    created_at: datetime


class ItemTransferResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    inventory_item_id: int
    movement_type: str
    from_location_id: int | None
    to_location_id: int | None
    created_by: int | None
    created_at: datetime


class StockTransferHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    purity_id: int
    source_location_id: int
    source_placement: str
    destination_location_id: int
    destination_placement: str
    weight: Decimal
    created_by: int
    created_at: datetime
