from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal

class CashEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    location_id: int
    service_sale_id: int | None
    sale_id: int | None
    return_id: int | None
    supplier_entry_id: int | None
    unit: str | None
    operation_id: int | None
    purchase_id: int | None
    description: str | None
    category: str | None
    kind: str
    amount_usd: Decimal
    created_by: int
    created_at: datetime


class ReconciliationCreate(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=100)
    location_id: int
    from_at: AwareDatetime
    to_at: AwareDatetime
    opening_usd: Decimal = Field(ge=0, decimal_places=2, max_digits=14)
    counted_usd: Decimal = Field(ge=0, decimal_places=2, max_digits=14)

    @model_validator(mode="after")
    def ordered_period(self):
        if self.from_at >= self.to_at or self.to_at > datetime.now(UTC):
            raise ValueError("Use a completed period with from_at before to_at")
        return self


class ReconciliationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    location_id: int
    from_at: datetime
    to_at: datetime
    opening_usd: Decimal
    expected_usd: Decimal
    counted_usd: Decimal
    variance_usd: Decimal
    created_by: int
    created_at: datetime

class CashSummaryResponse(BaseModel):
    service_received_usd: Decimal
    received_usd: Decimal
    refunded_usd: Decimal
    supplier_sent_usd: Decimal
    supplier_received_usd: Decimal
    expenses_usd: Decimal
    withdrawals_usd: Decimal
    supplier_reversals_usd: Decimal
    customer_purchases_usd: Decimal
    capital_usd: Decimal
    adjustments_usd: Decimal
    transfers_usd: Decimal
    internal_payments_usd: Decimal
    production_costs_usd: Decimal
    net_usd: Decimal

class CashOutflowCreate(BaseModel):
    location_id: int = Field(gt=0)
    kind: Literal["expense", "withdrawal"]
    amount_usd: Decimal = Field(gt=0, decimal_places=2, max_digits=14)
    description: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
    ]
    category: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)] | None
    ) = None