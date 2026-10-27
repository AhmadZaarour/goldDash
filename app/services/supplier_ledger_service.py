from decimal import Decimal

from sqlalchemy import select
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
    db.add(
        SupplierLedgerEntry(
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
    )


async def supplier_balance(db: AsyncSession, supplier_id: int):
    entries = await db.scalars(
        select(SupplierLedgerEntry).where(SupplierLedgerEntry.supplier_id == supplier_id)
    )
    gold = {}
    usd = Decimal("0")
    for entry in entries:
        if entry.purity_id is not None:
            gold[entry.purity_id] = gold.get(entry.purity_id, Decimal("0")) + entry.gold_grams
        usd += entry.making_usd
    return {"supplier_id": supplier_id, "gold_grams_by_purity": gold, "making_usd": usd}
