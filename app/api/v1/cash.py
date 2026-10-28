from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import AdminUser, CashierUser
from app.core.database import get_db
from app.core.pagination import paginate
from app.models import Location
from app.models.cashLedger import CashEntry, CashReconciliation

router = APIRouter(prefix="/cash", tags=["Cash"])
Database = Annotated[AsyncSession, Depends(get_db)]


class CashEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    location_id: int
    sale_id: int | None
    return_id: int | None
    supplier_entry_id: int | None
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


def period_statement(location_id, from_at, to_at):
    statement = select(CashEntry).where(CashEntry.location_id == location_id)
    if from_at is not None:
        statement = statement.where(CashEntry.created_at >= from_at)
    if to_at is not None:
        statement = statement.where(CashEntry.created_at < to_at)
    return statement


@router.get("/entries", response_model=list[CashEntryResponse])
async def entries(
    db: Database,
    response: Response,
    user: CashierUser,
    location_id: int = Query(gt=0),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    from_at: AwareDatetime | None = None,
    to_at: AwareDatetime | None = None,
):
    if from_at and to_at and from_at >= to_at:
        raise HTTPException(422, "from_at must be before to_at")
    return await paginate(
        db,
        period_statement(location_id, from_at, to_at).order_by(CashEntry.id),
        response,
        limit,
        offset,
    )


class CashSummaryResponse(BaseModel):
    received_usd: Decimal
    refunded_usd: Decimal
    supplier_sent_usd: Decimal
    supplier_received_usd: Decimal
    supplier_reversals_usd: Decimal
    net_usd: Decimal


@router.get("/summary", response_model=CashSummaryResponse)
async def summary(
    db: Database,
    user: CashierUser,
    location_id: int = Query(gt=0),
    from_at: AwareDatetime | None = None,
    to_at: AwareDatetime | None = None,
):
    if from_at and to_at and from_at >= to_at:
        raise HTTPException(422, "from_at must be before to_at")
    period = period_statement(location_id, from_at, to_at).subquery()
    rows = await db.execute(
        select(period.c.kind, func.sum(period.c.amount_usd)).group_by(period.c.kind)
    )
    totals = dict(rows.all())
    zero = Decimal("0")
    return {
        "received_usd": totals.get("sale", zero),
        "refunded_usd": -totals.get("refund", zero),
        "supplier_sent_usd": -totals.get("supplier_sent", zero),
        "supplier_received_usd": totals.get("supplier_received", zero),
        "supplier_reversals_usd": totals.get("supplier_reversal", zero),
        "net_usd": sum(totals.values(), zero),
    }


@router.post("/reconciliations", response_model=ReconciliationResponse, status_code=201)
async def reconcile(data: ReconciliationCreate, db: Database, user: AdminUser):
    if await db.get(Location, data.location_id) is None:
        raise HTTPException(404, "Location not found")
    period = period_statement(data.location_id, data.from_at, data.to_at).subquery()
    net = await db.scalar(select(func.coalesce(func.sum(period.c.amount_usd), 0)))
    expected = data.opening_usd + net
    record = CashReconciliation(
        source_key=data.idempotency_key,
        location_id=data.location_id,
        from_at=data.from_at,
        to_at=data.to_at,
        opening_usd=data.opening_usd,
        expected_usd=expected,
        counted_usd=data.counted_usd,
        variance_usd=data.counted_usd - expected,
        created_by=user.id,
    )
    db.add(record)
    try:
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(409, "Reconciliation key already used") from error
    await db.refresh(record)
    return record


@router.get("/reconciliations", response_model=list[ReconciliationResponse])
async def reconciliations(
    db: Database,
    response: Response,
    user: AdminUser,
    location_id: int = Query(gt=0),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    return await paginate(
        db,
        select(CashReconciliation)
        .where(CashReconciliation.location_id == location_id)
        .order_by(CashReconciliation.id),
        response,
        limit,
        offset,
    )
