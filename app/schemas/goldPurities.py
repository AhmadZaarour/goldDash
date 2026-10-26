from pydantic import BaseModel, ConfigDict

class GoldPurityCreate(BaseModel):
    name: str
    karat: int
    purity: float

class GoldPurityUpdate(BaseModel):
    name: str
    karat: int
    purity: float

class GoldPurityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    karat: int
    purity: float
