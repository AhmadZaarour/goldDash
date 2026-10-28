from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.supplierLedger import SupplierLedgerEntry


def post_entry(
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
):
    """Post within the caller's transaction; never commit part of an invoice."""
    gold, usd = Decimal(str(gold_grams)), Decimal(str(making_usd))
    if gold == 0 and usd == 0:
        return
    entry = SupplierLedgerEntry(
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
    gold, usd = {}, Decimal("0")
    for purity_id, grams, making in rows:
        if purity_id is not None:
            gold[purity_id] = grams
        usd += making
    return {"supplier_id": supplier_id, "gold_grams_by_purity": gold, "making_usd": usd}
