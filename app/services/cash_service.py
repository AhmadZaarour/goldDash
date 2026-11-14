from decimal import Decimal

from fastapi import HTTPException, Query, Response
from pydantic import AwareDatetime
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import AdminUser
from app.core.pagination import paginate
from app.models import Location
from app.models.cashLedger import CashEntry, CashReconciliation
from app.services.idempotency import IdempotencyKey, claim_operation, complete_operation
from app.services.transaction_validation import require_active_location
from app.schemas.cash import (
    CashEntryResponse,
    CashOutflowCreate,
    ReconciliationCreate,
)

Database = AsyncSession

def period_statement(location_id, from_at, to_at):
    statement = select(CashEntry).where(CashEntry.location_id == location_id)
    if from_at is not None:
        statement = statement.where(CashEntry.created_at >= from_at)
    if to_at is not None:
        statement = statement.where(CashEntry.created_at < to_at)
    return statement

async def summary_service(
    db: Database,
    location_id: int = Query(gt=0),
    from_at: AwareDatetime | None = None,
    to_at: AwareDatetime | None = None,
) -> dict[str, Decimal]:
    if from_at and to_at and from_at >= to_at:
        raise HTTPException(422, "from_at must be before to_at")
    period = period_statement(location_id, from_at, to_at).subquery()
    rows = await db.execute(
        select(period.c.kind, func.sum(period.c.amount_usd)).group_by(period.c.kind)
    )
    totals = dict(rows.all())
    zero = Decimal("0")

    return {
        "service_received_usd": totals.get("service_sale", zero),
        "received_usd": totals.get("sale", zero),
        "refunded_usd": -totals.get("refund", zero),
        "supplier_sent_usd": -totals.get("supplier_sent", zero),
        "supplier_received_usd": totals.get("supplier_received", zero),
        "supplier_reversals_usd": totals.get("supplier_reversal", zero),
        "expenses_usd": -totals.get("expense", zero),
        "withdrawals_usd": -totals.get("withdrawal", zero),
        "customer_purchases_usd": -totals.get("customer_purchase", zero),
        "capital_usd": totals.get("capital", zero),
        "adjustments_usd": totals.get("adjustment", zero),
        "transfers_usd": totals.get("cash_transfer", zero),
        "internal_payments_usd": totals.get("internal_payment", zero),
        "production_costs_usd": -totals.get("production_cost", zero),
        "net_usd": sum(totals.values(), zero),
    }

async def reconcile_service(
    data: ReconciliationCreate,
    db: Database,
    user: AdminUser,
    ) -> CashReconciliation:

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

async def reconciliations_service(
    db: Database,
    response: Response,
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

async def record_outflow_service(
    data: CashOutflowCreate,
    db: Database,
    user: AdminUser,
    idempotency_key: IdempotencyKey,
) -> CashEntryResponse:
    receipt, replayed = await claim_operation(db, user.id, "cash:outflow", idempotency_key, data)
    if replayed:
        return CashEntryResponse.model_validate(receipt.response_data)
    try:
        await require_active_location(db, data.location_id)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    entry = CashEntry(
        location_id=data.location_id,
        kind=data.kind,
        amount_usd=-data.amount_usd,
        description=data.description,
        category=data.category,
        created_by=user.id,
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    result = CashEntryResponse.model_validate(entry)
    await complete_operation(db, receipt, result)
    return result