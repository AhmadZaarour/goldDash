from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.schemas.operations import GoldLine, ProducedPiece

Weight = Annotated[Decimal, Field(gt=0, decimal_places=3, max_digits=12)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class WeightByPurity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    purity_id: int = Field(gt=0)
    weight: Weight


class ProductionStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    location_id: int = Field(gt=0)
    reference: str | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=500)
    inputs: list[WeightByPurity] = Field(min_length=1, max_length=100)
    direct_cost_usd: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2, max_digits=14)


class ProductionStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name
    outputs: list[WeightByPurity] = Field(min_length=1, max_length=100)
    scrap: list[WeightByPurity] = Field(default_factory=list, max_length=100)
    note: str | None = Field(default=None, max_length=500)
    direct_cost_usd: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2, max_digits=14)
    expected_step: int = Field(ge=0)


class ProductionFinish(BaseModel):
    expected_step: int = Field(ge=1)


class WeightTradeRow(WeightByPurity):
    making_per_gram: Decimal = Field(ge=0, decimal_places=4, max_digits=14)


class FactorySaleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    location_id: int = Field(gt=0)
    supplier_id: int = Field(gt=0)
    invoice_number: str | None = Field(default=None, max_length=50)
    note: str | None = Field(default=None, max_length=200)
    lines: list[WeightTradeRow] = Field(min_length=1, max_length=100)


class WeightSupplyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    location_id: int = Field(gt=0)
    showroom_location_id: int = Field(gt=0)
    gold_price_usd: Decimal = Field(gt=0, decimal_places=4, max_digits=14)
    note: str | None = Field(default=None, max_length=500)
    lines: list[WeightTradeRow] = Field(min_length=1, max_length=100)


class ShowroomReceive(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pieces: list[ProducedPiece] = Field(min_length=1, max_length=100)


class FinishedSeed(BaseModel):
    model_config = ConfigDict(extra="forbid")
    location_id: int = Field(gt=0)
    gold: list[GoldLine] = Field(min_length=1, max_length=100)
    note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
