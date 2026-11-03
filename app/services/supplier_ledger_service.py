from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.goldPurities import GoldPurity
from app.models.supplierLedger import SupplierLedgerEntry
from app.services.gold_conversion import grams24, purchase_factor


async def post_entry(
    db: AsyncSession,
    *,
    supplier_id: int,
    purity_id: int | None,
    gold_grams,
    making_usd,
    source_key: str,
    kind: str,
    created_by: int,
    purchase_id: int | None = None,
    sale_id: int | None = None,
    gold_24k: Decimal | None = None,
    valuation_factor: Decimal | None = None,
):
    """Post within the caller's transaction; never commit part of an invoice."""
    gold, usd = Decimal(str(gold_grams)), Decimal(str(making_usd))
    if gold == 0 and usd == 0:
        return
    factor = valuation_factor or Decimal(1)
    if gold_24k is None:
        if gold:
            purity = await db.get(GoldPurity, purity_id)
            if purity is None:
                raise ValueError("Purity not found")
            factor = purchase_factor(purity)
        gold_24k = grams24(gold, factor)
    entry = SupplierLedgerEntry(
        gold_24k=gold_24k,
        valuation_factor=factor,
        supplier_id=supplier_id,
        purity_id=purity_id,
        gold_grams=gold,
        making_usd=usd,
        source_key=source_key,
        kind=kind,
        created_by=created_by,
        purchase_id=purchase_id,
        sale_id=sale_id,
    )
    db.add(entry)
    return entry


async def supplier_balance(db: AsyncSession, supplier_id: int):
    rows = await db.execute(
        select(
            SupplierLedgerEntry.purity_id,
            func.sum(SupplierLedgerEntry.gold_grams),
            func.sum(SupplierLedgerEntry.making_usd),
        )
        .where(SupplierLedgerEntry.supplier_id == supplier_id)
        .group_by(SupplierLedgerEntry.purity_id)
    )
    total24 = await db.scalar(
        select(func.coalesce(func.sum(SupplierLedgerEntry.gold_24k), 0)).where(
            SupplierLedgerEntry.supplier_id == supplier_id
        )
    )
    gold, usd = {}, Decimal("0")
    for purity_id, grams, making in rows:
        if purity_id is not None:
            gold[purity_id] = grams
        usd += making
    return {
        "supplier_id": supplier_id,
        "gold_grams_by_purity": gold,
        "making_usd": usd,
        "gold_24k": total24,
        "is_settled": usd == 0 and total24 == 0,
    }
