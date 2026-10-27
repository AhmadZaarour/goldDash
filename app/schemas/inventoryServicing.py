from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

class ServiceCreate(BaseModel):
    notes: str | None = Field(default=None, max_length=200)
    customer_id: int
    barcode: str | None = Field(min_length=1, max_length=50)
    status: str | None = Field(default=None, min_length=1, max_length=50)
    cost: float
    created_at: datetime | None = Field(default_factory=datetime.utcnow)

class ServiceUpdate(BaseModel):
    notes:  str | None = Field(default=None, max_length=200)
    status: str | None = Field(default=None, min_length=1, max_length=50)
    cost: float
    
class ServiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    notes: str
    customer_id: int
    barcode: str
    status: str
    cost: float
    created_at: datetime