from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime

class SaleBookCreate(BaseModel):
    sale_id: int
    recieved_gold_charge: float
    recieved_making_charge: float
    updated_at: datetime | None = Field(default_factory=datetime.utcnow)

class SaleBookUpdate(BaseModel):
    sale_id: int | None = None
    recieved_gold_charge: float | None = None
    recieved_making_charge: float | None = None
    updated_at: datetime | None = Field(default_factory=datetime.utcnow)

class SaleBookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sale_id: int
    recieved_gold_charge: float
    recieved_making_charge: float
    updated_at: datetime
    