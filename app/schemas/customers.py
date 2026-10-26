from datetime import datetime

from pydantic import BaseModel, ConfigDict

class CustomerCreate(BaseModel):
    name: str
    phone: str

class CustomerUpdate(BaseModel):
    name: str
    phone: str

class CustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: str
    created_at: datetime