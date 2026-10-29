"""Move the physical resources behind a supplier settlement in its transaction."""

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cashLedger import CashEntry
from app.models.inventoryBalance import InventoryBalance


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
):
    # Caller holds an exclusive location lock, acquired before any stock row lock.
    # Other cash writers hold shared location locks through commit.
    if cash_delta < 0 and await available_cash(db, location_id) < -cash_delta:
        raise ValueError("Insufficient cash in the selected drawer")
    if not gold_delta:
        return
    balance = await db.scalar(
        select(InventoryBalance)
        .where(
            InventoryBalance.location_id == location_id,
            InventoryBalance.purity_id == purity_id,
            InventoryBalance.placement == placement,
        )
        .with_for_update()
    )
    if gold_delta < 0 and (balance is None or balance.total_weight < -gold_delta):
        raise ValueError("Insufficient bulk gold at the selected location, placement and purity")
    if balance is not None:
        balance.total_weight += gold_delta
    else:
        statement = insert(InventoryBalance).values(
            location_id=location_id,
            purity_id=purity_id,
            placement=placement,
            total_weight=gold_delta,
        )
        await db.execute(
            statement.on_conflict_do_update(
                constraint="uq_balance_bucket",
                set_={"total_weight": InventoryBalance.total_weight + gold_delta},
            )
        )
