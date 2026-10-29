from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import AdminUser
from app.core.database import get_db
from app.core.dependencies import CurrentUser
from app.core.pagination import paginate
from app.models import GoldPurity, Location, Supplier
from app.models.cashLedger import CashEntry
from app.models.inventoryBalance import InventoryBalance
from app.models.supplierLedger import SupplierLedgerEntry
from app.services.settlement_resources import available_cash, move_resources
from app.services.supplier_ledger_service import post_entry, supplier_balance
from app.services.transaction_validation import require_active_location, require_active_supplier

router = APIRouter(prefix="/suppliers", tags=["Supplier ledger"])


class SettlementCreate(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=80)
    direction: Literal["sent", "received"]
    location_id: int | None = Field(default=None, gt=0)
    purity_id: int | None = Field(default=None, gt=0)
    placement: Literal["factory", "showroom"] = "factory"
    close_account: bool = False
    gold_grams: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=3)
    making_usd: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)

    @model_validator(mode="after")
    def valid_units(self):
        if self.gold_grams == 0 and self.making_usd == 0:
            raise ValueError("A settlement must contain gold or USD")
        if self.gold_grams and self.purity_id is None:
            raise ValueError("Gold settlements require a purity")
        if self.location_id is None:
            raise ValueError("Settlements require a location for cash or gold")
        return self


class SupplierBalanceResponse(BaseModel):
    supplier_id: int
    gold_grams_by_purity: dict[int, Decimal]
    making_usd: Decimal
    is_settled: bool


class AvailabilityResponse(BaseModel):
    cash_usd: Decimal
    gold_grams_by_purity: dict[int, Decimal]


@router.get("/{supplier_id}/availability", response_model=AvailabilityResponse)
async def availability(
    supplier_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: AdminUser,
    location_id: int = Query(gt=0),
    placement: Literal["factory", "showroom"] = "factory",
):
    if await db.get(Supplier, supplier_id) is None:
        raise HTTPException(404, "Supplier not found")
    if await db.get(Location, location_id) is None:
        raise HTTPException(404, "Location not found")
    rows = await db.execute(
        select(InventoryBalance.purity_id, InventoryBalance.total_weight).where(
            InventoryBalance.location_id == location_id, InventoryBalance.placement == placement
        )
    )
    return {
        "cash_usd": await available_cash(db, location_id),
        "gold_grams_by_purity": dict(rows.all()),
    }


@router.get("/{supplier_id}/balance", response_model=SupplierBalanceResponse)
async def get_balance(
    supplier_id: int, db: Annotated[AsyncSession, Depends(get_db)], user: CurrentUser
):
    if await db.get(Supplier, supplier_id) is None:
        raise HTTPException(404, "Supplier not found")
    return await supplier_balance(db, supplier_id)


@router.post("/{supplier_id}/settlements", status_code=201, response_model=SupplierBalanceResponse)
async def settle(
    supplier_id: int,
    data: SettlementCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: AdminUser,
):
    try:
        # Keep location -> supplier -> stock lock order consistent with trading.
        await require_active_location(db, data.location_id, exclusive=True)
        await require_active_supplier(db, supplier_id, exclusive=True)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    if data.purity_id is not None and await db.get(GoldPurity, data.purity_id) is None:
        raise HTTPException(404, "Purity not found")
    sign = -1 if data.direction == "sent" else 1
    key = f"settlement:{supplier_id}:{data.idempotency_key}"
    if await db.scalar(select(SupplierLedgerEntry.id).where(SupplierLedgerEntry.source_key == key)):
        raise HTTPException(409, "Settlement key already used")
    before = await supplier_balance(db, supplier_id)
    remaining_gold = dict(before["gold_grams_by_purity"])
    if data.gold_grams:
        remaining_gold[data.purity_id] = (
            remaining_gold.get(data.purity_id, Decimal(0)) + sign * data.gold_grams
        )
    if data.close_account and (
        before["making_usd"] + sign * data.making_usd != 0
        or any(value != 0 for value in remaining_gold.values())
    ):
        raise HTTPException(
            409, "Account can only be settled when USD and every purity balance are zero"
        )
    try:
        await move_resources(
            db,
            location_id=data.location_id,
            purity_id=data.purity_id,
            placement=data.placement,
            gold_delta=sign * data.gold_grams,
            cash_delta=sign * data.making_usd,
        )
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    entry = post_entry(
        db,
        supplier_id=supplier_id,
        purity_id=data.purity_id,
        gold_grams=sign * data.gold_grams,
        making_usd=sign * data.making_usd,
        source_key=key,
        kind="settlement",
        created_by=user.id,
    )
    entry.location_id = data.location_id
    entry.placement = data.placement if data.gold_grams else None
    try:
        if data.making_usd:
            await db.flush()
            db.add(
                CashEntry(
                    location_id=data.location_id,
                    supplier_entry_id=entry.id,
                    kind=f"supplier_{data.direction}",
                    amount_usd=sign * data.making_usd,
                    created_by=user.id,
                )
            )
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(409, "Settlement conflict") from error
    return await supplier_balance(db, supplier_id)


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
    making_usd: Decimal
    reversal_of_id: int | None
    note: str | None
    created_by: int
    created_at: datetime


class ReversalCreate(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=1, max_length=500)


@router.get("/{supplier_id}/ledger", response_model=list[LedgerEntryResponse])
async def history(
    supplier_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    response: Response,
    user: CurrentUser,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    purity_id: int | None = Query(None, gt=0),
    kind: Literal["purchase", "sale", "settlement", "reversal"] | None = None,
    from_at: AwareDatetime | None = None,
    to_at: AwareDatetime | None = None,
):
    if await db.get(Supplier, supplier_id) is None:
        raise HTTPException(404, "Supplier not found")
    if from_at and to_at and from_at >= to_at:
        raise HTTPException(422, "from_at must be before to_at")
    statement = select(SupplierLedgerEntry).where(SupplierLedgerEntry.supplier_id == supplier_id)
    if purity_id is not None:
        statement = statement.where(SupplierLedgerEntry.purity_id == purity_id)
    if kind:
        statement = statement.where(SupplierLedgerEntry.kind == kind)
    if from_at:
        statement = statement.where(SupplierLedgerEntry.created_at >= from_at)
    if to_at:
        statement = statement.where(SupplierLedgerEntry.created_at < to_at)
    return await paginate(db, statement.order_by(SupplierLedgerEntry.id), response, limit, offset)


@router.post(
    "/{supplier_id}/ledger/{entry_id}/reverse", response_model=LedgerEntryResponse, status_code=201
)
async def reverse_settlement(
    supplier_id: int,
    entry_id: int,
    data: ReversalCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: AdminUser,
):
    original = await db.scalar(
        select(SupplierLedgerEntry).where(
            SupplierLedgerEntry.id == entry_id, SupplierLedgerEntry.supplier_id == supplier_id
        )
    )
    if original is None:
        raise HTTPException(404, "Ledger entry not found")
    if original.location_id is not None:
        await db.scalar(
            select(Location).where(Location.id == original.location_id).with_for_update()
        )
    await db.scalar(select(Supplier).where(Supplier.id == supplier_id).with_for_update())
    # Serialize concurrent reversals and settlements on the supplier lock.
    if original.kind != "settlement":
        raise HTTPException(
            409, "Only settlements can be reversed here; invoices require a return workflow"
        )
    if await db.scalar(
        select(SupplierLedgerEntry.id).where(SupplierLedgerEntry.reversal_of_id == original.id)
    ):
        raise HTTPException(409, "Settlement already reversed")
    if original.location_id is not None:
        try:
            await move_resources(
                db,
                location_id=original.location_id,
                purity_id=original.purity_id,
                placement=original.placement,
                gold_delta=-original.gold_grams if original.placement else Decimal(0),
                cash_delta=-original.making_usd,
            )
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
    reversal = SupplierLedgerEntry(
        supplier_id=supplier_id,
        purity_id=original.purity_id,
        source_key=f"reversal:{supplier_id}:{data.idempotency_key}",
        kind="reversal",
        gold_grams=-original.gold_grams,
        making_usd=-original.making_usd,
        reversal_of_id=original.id,
        location_id=original.location_id,
        placement=original.placement,
        note=data.reason,
        created_by=user.id,
    )
    db.add(reversal)
    try:
        original_cash = await db.scalar(
            select(CashEntry).where(CashEntry.supplier_entry_id == original.id)
        )
        if original_cash is not None:
            await db.flush()
            db.add(
                CashEntry(
                    location_id=original_cash.location_id,
                    supplier_entry_id=reversal.id,
                    kind="supplier_reversal",
                    amount_usd=-original_cash.amount_usd,
                    created_by=user.id,
                )
            )
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(409, "Reversal conflict") from error
    await db.refresh(reversal)
    return reversal
