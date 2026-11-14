"""Supplier gold/USD balances, settlements and audit responses."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SettlementCreate(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=80)
    direction: Literal["sent", "received"]
    location_id: int | None = Field(default=None, gt=0)
    purity_id: int | None = Field(default=None, gt=0)
    placement: Literal["factory", "showroom"] = "factory"
    close_account: bool = False
    gold_grams: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=3)
    making_usd: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)

    cash_gold_usd: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    gold_price_usd: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=4)

    @model_validator(mode="after")
    def valid_units(self):
        if self.gold_grams == 0 and self.making_usd == 0 and self.cash_gold_usd == 0:
            raise ValueError("A settlement must contain gold or USD")
        if self.gold_grams and self.purity_id is None:
            raise ValueError("Gold settlements require a purity")
        if self.cash_gold_usd and self.gold_price_usd is None:
            raise ValueError("Cash substitution requires USD per 24K-equivalent gram")
        if self.location_id is None:
            raise ValueError("Settlements require a location for cash or gold")
        return self


class SupplierBalanceResponse(BaseModel):
    supplier_id: int
    gold_grams_by_purity: dict[int, Decimal]
    gold_24k: Decimal
    making_usd: Decimal
    is_settled: bool


class AvailabilityResponse(BaseModel):
    cash_usd: Decimal
    gold_grams_by_purity: dict[int, Decimal]


class LedgerEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    supplier_id: int
    purity_id: int | None
    location_id: int | None
    placement: str | None
    purchase_id: int | None
    sale_id: int | None
    kind: str
    source_key: str
    gold_grams: Decimal
    gold_24k: Decimal
    valuation_factor: Decimal
    physical_purity_id: int | None
    physical_gold_grams: Decimal | None
    cash_gold_usd: Decimal | None
    gold_price_usd: Decimal | None
    stock_value_usd: Decimal | None
    making_usd: Decimal
    reversal_of_id: int | None
    note: str | None
    created_by: int
    created_at: datetime


class ReversalCreate(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=1, max_length=500)
