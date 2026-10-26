from pydantic import BaseModel, ConfigDict

class LocationCreate(BaseModel):
    name: str
    code: str
    address: str
    is_active: bool = True

class LocationUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    address: str | None = None
    is_active: bool | None = None

class LocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str
    address: str | None
    is_active: bool