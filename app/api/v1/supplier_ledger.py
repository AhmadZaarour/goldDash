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
from app.models import GoldPurity, Supplier
from app.models.cashLedger import CashEntry
from app.models.supplierLedger import SupplierLedgerEntry
from app.services.supplier_ledger_service import post_entry, supplier_balance
from app.services.transaction_validation import require_active_location, require_active_supplier

router = APIRouter(prefix="/suppliers", tags=["Supplier ledger"])


class SettlementCreate(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=80)
    direction: Literal["sent", "received"]
    location_id: int | None = Field(default=None, gt=0)
    purity_id: int | None = None
    gold_grams: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=3)
    making_usd: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)

    @model_validator(mode="after")
    def valid_units(self):
        if self.gold_grams == 0 and self.making_usd == 0:
            raise ValueError("A settlement must contain gold or USD")
        if self.gold_grams and self.purity_id is None:
            raise ValueError("Gold settlements require a purity")
        if self.making_usd and self.location_id is None:
            raise ValueError("USD cash settlements require a location")
        return self


class SupplierBalanceResponse(BaseModel):
    supplier_id: int
    gold_grams_by_purity: dict[int, Decimal]
    making_usd: Decimal


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
        await require_active_supplier(db, supplier_id)
        if data.location_id is not None:
            await require_active_location(db, data.location_id)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    if data.purity_id is not None and await db.get(GoldPurity, data.purity_id) is None:
        raise HTTPException(404, "Purity not found")
    sign = -1 if data.direction == "sent" else 1
    key = f"settlement:{supplier_id}:{data.idempotency_key}"
    if await db.scalar(select(SupplierLedgerEntry.id).where(SupplierLedgerEntry.source_key == key)):
        raise HTTPException(409, "Settlement key already used")
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
        select(SupplierLedgerEntry)
        .where(SupplierLedgerEntry.id == entry_id, SupplierLedgerEntry.supplier_id == supplier_id)
        .with_for_update()
    )
    if original is None:
        raise HTTPException(404, "Ledger entry not found")
    if original.kind != "settlement":
        raise HTTPException(
            409, "Only settlements can be reversed here; invoices require a return workflow"
        )
    if await db.scalar(
        select(SupplierLedgerEntry.id).where(SupplierLedgerEntry.reversal_of_id == original.id)
    ):
        raise HTTPException(409, "Settlement already reversed")
    reversal = SupplierLedgerEntry(
        supplier_id=supplier_id,
        purity_id=original.purity_id,
        source_key=f"reversal:{supplier_id}:{data.idempotency_key}",
        kind="reversal",
        gold_grams=-original.gold_grams,
        making_usd=-original.making_usd,
        reversal_of_id=original.id,
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
