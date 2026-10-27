from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentUser
from app.models import GoldPurity, Supplier
from app.models.supplierLedger import SupplierLedgerEntry
from app.services.supplier_ledger_service import post_entry, supplier_balance

router = APIRouter(prefix="/suppliers", tags=["Supplier ledger"])


class SettlementCreate(BaseModel):
    idempotency_key: str = Field(min_length=1, max_length=80)
    direction: Literal["sent", "received"]
    purity_id: int | None = None
    gold_grams: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=3)
    making_usd: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)

    @model_validator(mode="after")
    def valid_units(self):
        if self.gold_grams == 0 and self.making_usd == 0:
            raise ValueError("A settlement must contain gold or USD")
        if self.gold_grams and self.purity_id is None:
            raise ValueError("Gold settlements require a purity")
        return self


@router.get("/{supplier_id}/balance")
async def get_balance(
    supplier_id: int, db: Annotated[AsyncSession, Depends(get_db)], user: CurrentUser
):
    if await db.get(Supplier, supplier_id) is None:
        raise HTTPException(404, "Supplier not found")
    return await supplier_balance(db, supplier_id)


@router.post("/{supplier_id}/settlements", status_code=201)
async def settle(
    supplier_id: int,
    data: SettlementCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: CurrentUser,
):
    if await db.get(Supplier, supplier_id) is None:
        raise HTTPException(404, "Supplier not found")
    if data.purity_id is not None and await db.get(GoldPurity, data.purity_id) is None:
        raise HTTPException(404, "Purity not found")
    sign = -1 if data.direction == "sent" else 1
    key = f"settlement:{data.idempotency_key}"
    if await db.scalar(select(SupplierLedgerEntry.id).where(SupplierLedgerEntry.source_key == key)):
        raise HTTPException(409, "Settlement key already used")
    post_entry(
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
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(409, "Settlement conflict") from error
    return await supplier_balance(db, supplier_id)
