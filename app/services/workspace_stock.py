"""Owned bulk stock and recorded carrying values, locked in the caller's transaction."""

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventoryBalance import InventoryBalance
from app.services.transaction_validation import require_active_location

VALUE = Decimal("0.0001")


def value4(value):
    return Decimal(value).quantize(VALUE, rounding=ROUND_HALF_UP)


async def lock_locations(db: AsyncSession, *ids: int):
    for id in sorted(set(ids)):
        await require_active_location(db, id, exclusive=True)


async def change_stock(db, *, unit, location_id, purity_id, placement, delta, value=None):
    row = await db.scalar(
        select(InventoryBalance)
        .where(
            InventoryBalance.unit == unit,
            InventoryBalance.location_id == location_id,
            InventoryBalance.purity_id == purity_id,
            InventoryBalance.placement == placement,
        )
        .with_for_update()
    )
    delta = Decimal(delta)
    if delta < 0 and (row is None or row.total_weight < -delta):
        raise ValueError("Insufficient bulk gold in this workspace and location")
    if row is None:
        row = InventoryBalance(
            unit=unit,
            location_id=location_id,
            purity_id=purity_id,
            placement=placement,
            total_weight=0,
            cost_usd=Decimal(0),
        )
        db.add(row)
        await db.flush()
    before = row.total_weight
    if delta < 0:
        removed = value4(row.cost_usd * -delta / before) if row.cost_usd is not None else None
        if value is not None:
            removed = value4(value)
            if row.cost_usd is None or row.cost_usd < removed:
                raise ValueError("The recorded stock value cannot cover this reversal")
        row.total_weight += delta
        if row.cost_usd is not None:
            row.cost_usd -= removed
        return removed
    row.total_weight += delta
    if value is None:
        row.cost_usd = None
    elif before == 0:
        row.cost_usd = value4(value)
    elif row.cost_usd is not None:
        row.cost_usd += value4(value)
    return value4(value) if value is not None else None
