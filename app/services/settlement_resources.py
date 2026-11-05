"""Move the physical resources behind a supplier settlement in its transaction."""

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.workspace import active_unit
from app.models.cashLedger import CashEntry


async def available_cash(db: AsyncSession, location_id: int) -> Decimal:
    return await db.scalar(
        select(func.coalesce(func.sum(CashEntry.amount_usd), 0)).where(
            CashEntry.location_id == location_id
        )
    )


async def move_resources(
    db: AsyncSession,
    *,
    location_id: int,
    purity_id: int | None,
    placement: str | None,
    gold_delta: Decimal,
    cash_delta: Decimal,
    gold_value_usd: Decimal | None = None,
):
    # Caller holds an exclusive location lock, acquired before any stock row lock.
    # Other cash writers hold shared location locks through commit.
    if cash_delta < 0 and await available_cash(db, location_id) < -cash_delta:
        raise ValueError("Insufficient cash in the selected drawer")
    if not gold_delta:
        return
    from app.services.workspace_stock import change_stock

    return await change_stock(
        db,
        unit=active_unit(),
        location_id=location_id,
        purity_id=purity_id,
        placement=placement,
        delta=gold_delta,
        value=gold_value_usd,
    )
