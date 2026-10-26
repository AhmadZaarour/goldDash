from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime

class PurchaseBookCreate(BaseModel):
    purchase_id: int
    paid_gold_charge: float
    paid_making_charge: float
    updated_at: datetime | None = Field(default_factory=datetime.utcnow)

class PurchaseBookUpdate(BaseModel):
    purchase_id: int | None = None
    paid_gold_charge: float | None = None
    paid_making_charge: float | None = None
    updated_at: datetime | None = Field(default_factory=datetime.utcnow)

class PurchaseBookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    purchase_id: int
    paid_gold_charge: float
    paid_making_charge: float
    updated_at: datetime
