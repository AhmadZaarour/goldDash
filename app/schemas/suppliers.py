from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

class SupplierCreate(BaseModel):
    name: str
    phone: str
    is_active: bool = True

class SupplierUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    phone: str | None = Field(default=None, min_length=1, max_length=50)
    is_active: bool | None

class SupplierResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    phone: str
    is_active: bool
    created_at: datetime