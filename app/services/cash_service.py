from datetime import UTC, datetime
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
from app.schemas.cash import (
    CashEntryResponse,
    CashOutflowCreate,
    CashOutflowDetails,
    ReconciliationCounts,
    ReconciliationCreate,
)
from app.services.idempotency import IdempotencyKey, claim_operation, complete_operation
from app.services.transaction_validation import require_active_location

Database = AsyncSession


def period_statement(location_id, from_at, to_at):
    statement = select(CashEntry).where(CashEntry.location_id == location_id)
    if from_at is not None:
        statement = statement.where(CashEntry.created_at >= from_at)
    if to_at is not None:
        statement = statement.where(CashEntry.created_at < to_at)
    return statement


async def lock_cash_drawer(db: Database, location_id: int) -> None:
    """Serialize historical cash corrections with drawer closures and cash writers."""
    drawer = await db.scalar(
        select(Location.id).where(Location.id == location_id).with_for_update()
    )
    if drawer is None:
        raise HTTPException(404, "Location not found")


async def require_unreconciled_entry(db: Database, entry: CashEntry) -> None:
    closed = await db.scalar(
        select(CashReconciliation.id)
        .where(
            CashReconciliation.location_id == entry.location_id,
            CashReconciliation.voided_at.is_(None),
            CashReconciliation.from_at <= entry.created_at,
            CashReconciliation.to_at > entry.created_at,
        )
        .limit(1)
    )
    if closed is not None:
        raise HTTPException(409, "Void the reconciliation before correcting cash in this period")


def reconciliation_totals(
    opening: Decimal, counted: Decimal, net: Decimal
) -> tuple[Decimal, Decimal]:
    expected = opening + net
    variance = counted - expected
    if max(abs(expected), abs(variance)) >= Decimal("1e12"):
        raise HTTPException(422, "The calculated reconciliation amounts are too large")
    return expected, variance


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

    await lock_cash_drawer(db, data.location_id)
    period = period_statement(data.location_id, data.from_at, data.to_at).subquery()
    net = await db.scalar(select(func.coalesce(func.sum(period.c.amount_usd), 0)))
    expected, variance = reconciliation_totals(data.opening_usd, data.counted_usd, net)
    record = CashReconciliation(
        source_key=data.idempotency_key,
        location_id=data.location_id,
        from_at=data.from_at,
        to_at=data.to_at,
        opening_usd=data.opening_usd,
        expected_usd=expected,
        counted_usd=data.counted_usd,
        variance_usd=variance,
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
        original = CashEntryResponse.model_validate(receipt.response_data)
        if await db.get(CashEntry, original.id) is None:
            raise HTTPException(409, "This cash outflow was deleted")
        return original
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


async def correct_outflow(
    db: Database, entry_id: int, data: CashOutflowDetails | None
) -> CashEntry | None:
    location_id = await db.scalar(select(CashEntry.location_id).where(CashEntry.id == entry_id))
    if location_id is None:
        raise HTTPException(404, "Cash entry not found")
    await lock_cash_drawer(db, location_id)
    entry = await db.scalar(select(CashEntry).where(CashEntry.id == entry_id).with_for_update())
    if entry is None:
        raise HTTPException(404, "Cash entry not found")
    if entry.kind not in {"expense", "withdrawal"}:
        raise HTTPException(409, "Correct this cash entry from its original transaction")
    if data is None or -data.amount_usd != entry.amount_usd:
        await require_unreconciled_entry(db, entry)
    if data is None:
        await db.delete(entry)
        await db.commit()
        return None
    entry.amount_usd = -data.amount_usd
    entry.description = data.description
    entry.category = data.category
    await db.commit()
    return entry


async def correct_reconciliation(
    db: Database, record_id: int, data: ReconciliationCounts | None
) -> CashReconciliation:
    location_id = await db.scalar(
        select(CashReconciliation.location_id).where(CashReconciliation.id == record_id)
    )
    if location_id is None:
        raise HTTPException(404, "Reconciliation not found")
    await lock_cash_drawer(db, location_id)
    record = await db.scalar(
        select(CashReconciliation).where(CashReconciliation.id == record_id).with_for_update()
    )
    if record is None:
        raise HTTPException(404, "Reconciliation not found")
    if record.voided_at is not None:
        raise HTTPException(409, "This reconciliation was already voided")
    if data is None:
        record.voided_at = datetime.now(UTC)
    else:
        original_net = record.expected_usd - record.opening_usd
        record.expected_usd, record.variance_usd = reconciliation_totals(
            data.opening_usd, data.counted_usd, original_net
        )
        record.opening_usd = data.opening_usd
        record.counted_usd = data.counted_usd
    await db.commit()
    return record
