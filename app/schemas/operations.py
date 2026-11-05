from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, HttpUrl, model_validator

Unit = Literal["factory", "showroom"]
Placement = Literal["factory", "showroom"]


class GoldLine(BaseModel):
    purity_id: int = Field(gt=0)
    placement: Placement | None = None
    weight: Decimal = Field(decimal_places=3, max_digits=14)
    value_usd: Decimal | None = Field(default=None, ge=0, decimal_places=4, max_digits=18)


class CapitalCreate(BaseModel):
    effective_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def not_future(self):
        if self.effective_at is not None and self.effective_at > datetime.now(UTC):
            raise ValueError("Opening/addition dates cannot be in the future")
        return self

    location_id: int = Field(gt=0)
    cash_usd: Decimal = Field(default=Decimal(0), decimal_places=2, max_digits=14)
    gold: list[GoldLine] = Field(default_factory=list, max_length=100)
    note: str = Field(min_length=1, max_length=500)


class CashTransferCreate(BaseModel):
    location_id: int = Field(gt=0)
    to_unit: Unit
    to_location_id: int = Field(gt=0)
    amount_usd: Decimal = Field(gt=0, decimal_places=2, max_digits=14)
    note: str = Field(min_length=1, max_length=500)


class GoldTransferCreate(BaseModel):
    location_id: int = Field(gt=0)
    to_unit: Unit
    to_location_id: int = Field(gt=0)
    purity_id: int = Field(gt=0)
    weight: Decimal = Field(gt=0, decimal_places=3, max_digits=14)
    placement: Placement | None = None
    to_placement: Placement | None = None
    note: str = Field(min_length=1, max_length=500)


class StockValuationCreate(BaseModel):
    location_id: int = Field(gt=0)
    purity_id: int = Field(gt=0)
    placement: Placement | None = None
    value_usd: Decimal = Field(ge=0, decimal_places=4, max_digits=18)
    note: str = Field(min_length=1, max_length=500)


class ProducedPiece(BaseModel):
    product_id: int = Field(gt=0)
    weight: Decimal = Field(gt=0, decimal_places=3, max_digits=12)
    image_url: HttpUrl | None = Field(default=None, max_length=2048)
    photo_token: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")


class ProductionCreate(BaseModel):
    location_id: int = Field(gt=0)
    reference: str | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=500)
    inputs: list[GoldLine] = Field(min_length=1, max_length=100)
    pieces: list[ProducedPiece] = Field(min_length=1, max_length=100)
    scrap: list[GoldLine] = Field(default_factory=list, max_length=100)
    loss_gold_24k: Decimal = Field(default=Decimal(0), ge=0, decimal_places=3, max_digits=14)
    direct_cost_usd: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2, max_digits=14)

    @model_validator(mode="after")
    def weights(self):
        if any(line.weight <= 0 for line in self.inputs + self.scrap):
            raise ValueError("Production weights must be positive")
        if self.loss_gold_24k and not self.note:
            raise ValueError("Explain unrecoverable gold loss in the batch notes")
        return self


class InternalPiece(BaseModel):
    inventory_item_id: int = Field(gt=0)
    making_usd: Decimal = Field(ge=0, decimal_places=2, max_digits=14)


class InternalInvoiceCreate(BaseModel):
    location_id: int = Field(gt=0)
    showroom_location_id: int = Field(gt=0)
    pieces: list[InternalPiece] = Field(min_length=1, max_length=100)
    gold_price_usd: Decimal = Field(gt=0, decimal_places=4, max_digits=14)
    note: str | None = Field(default=None, max_length=500)


class SupplierItemSaleCreate(BaseModel):
    location_id: int = Field(gt=0)
    supplier_id: int = Field(gt=0)
    invoice_number: str | None = Field(default=None, max_length=50)
    pieces: list[InternalPiece] = Field(min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=200)


class InternalPaymentCreate(BaseModel):
    direction: Literal["showroom_to_factory", "factory_to_showroom"] = "showroom_to_factory"
    showroom_location_id: int = Field(gt=0)
    factory_location_id: int = Field(gt=0)
    purity_id: int | None = Field(default=None, gt=0)
    showroom_placement: Placement = "showroom"
    factory_placement: Placement = "factory"
    gold_grams: Decimal = Field(default=Decimal(0), ge=0, decimal_places=3, max_digits=14)
    making_usd: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2, max_digits=14)
    cash_gold_usd: Decimal = Field(default=Decimal(0), ge=0, decimal_places=2, max_digits=14)
    gold_price_usd: Decimal | None = Field(default=None, gt=0, decimal_places=4, max_digits=14)
    close_account: bool = False
    note: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def units(self):
        if not (self.gold_grams or self.making_usd or self.cash_gold_usd):
            raise ValueError("Enter a gold or cash payment")
        if self.gold_grams and self.purity_id is None:
            raise ValueError("Gold payments require a purity")
        if self.cash_gold_usd and self.gold_price_usd is None:
            raise ValueError("Cash substitution requires USD per 24K-equivalent gram")
        return self


class ReverseCreate(BaseModel):
    note: str = Field(min_length=1, max_length=500)


class LegacyAssignCreate(BaseModel):
    location_id: int | None = Field(default=None, gt=0)
    kind: Literal[
        "purchase",
        "sale",
        "cash",
        "stock",
        "item",
        "supplier_entry",
        "reconciliation",
        "return",
        "movement",
        "service",
        "transfer",
        "photo",
    ]
    id: int = Field(gt=0)
    unit: Unit
    note: str = Field(min_length=1, max_length=500)


class StaffWorkspaceUpdate(BaseModel):
    workspace_access: Literal["factory", "showroom", "both"]
