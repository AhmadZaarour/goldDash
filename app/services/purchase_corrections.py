"""Contextual purchase corrections that keep the financial and stock history."""

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.workspace import active_unit, in_workspace
from app.models import (
    CashEntry,
    InventoryBalance,
    InventoryItem,
    InventoryMovement,
    Location,
    Purchase,
    PurchaseBook,
    PurchaseItem,
    PurchaseStock,
    SaleItem,
    Supplier,
    SupplierLedgerEntry,
)
from app.models.operations import InternalInvoiceLine
from app.schemas.purchases import PurchaseUpdate
from app.services.operations_service import cash_entry, document
from app.services.workspace_stock import change_stock


async def locked_purchase(db: AsyncSession, purchase_id: int) -> Purchase:
    purchase = await db.scalar(select(Purchase).where(Purchase.id == purchase_id).with_for_update())
    if purchase is None:
        raise HTTPException(404, "Purchase not found in this workspace")
    return purchase


async def update_purchase(db: AsyncSession, purchase_id: int, data: PurchaseUpdate) -> Purchase:
    purchase = await locked_purchase(db, purchase_id)
    if purchase.voided_at is not None:
        raise HTTPException(409, "A voided purchase cannot be edited")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(purchase, field, value or None)
    await db.commit()
    return purchase


async def void_item_invoice(db: AsyncSession, purchase: Purchase, reason: str, user_id: int):
    # Use the same lock order as a settlement and keep the invoice's location available
    # for the correction even when it has since been marked inactive.
    await db.scalar(
        select(Location.id).where(Location.id == purchase.location_id).with_for_update(read=True)
    )
    await db.scalar(
        select(Supplier.id).where(Supplier.id == purchase.supplier_id).with_for_update()
    )
    line_ids = (
        await db.scalars(select(PurchaseItem.id).where(PurchaseItem.purchase_id == purchase.id))
    ).all()
    if not line_ids:
        raise ValueError("This legacy invoice has no reversible piece records")
    items = (
        await db.scalars(
            select(InventoryItem)
            .where(InventoryItem.purchase_item_id.in_(line_ids))
            .order_by(InventoryItem.id)
            .with_for_update(of=InventoryItem)
        )
    ).all()
    if len(items) != len(line_ids) or any(
        item.location_id != purchase.location_id
        or item.status != "in_stock"
        or item.acquisition_internal_id is not None
        for item in items
    ):
        raise ValueError("All pieces must be available at their purchase location")
    item_ids = [item.id for item in items]
    with in_workspace(None):
        linked = await db.scalar(
            select(
                or_(
                    select(InventoryMovement.id)
                    .where(
                        InventoryMovement.inventory_item_id.in_(item_ids),
                        InventoryMovement.movement_type != "purchase",
                    )
                    .exists(),
                    select(SaleItem.id).where(SaleItem.inventory_item_id.in_(item_ids)).exists(),
                    select(InternalInvoiceLine.id)
                    .where(InternalInvoiceLine.inventory_item_id.in_(item_ids))
                    .exists(),
                    select(PurchaseBook.id).where(PurchaseBook.purchase_id == purchase.id).exists(),
                )
            )
        )
    if linked:
        raise ValueError("A piece has already moved or the purchase has linked transactions")
    entries = (
        await db.scalars(
            select(SupplierLedgerEntry).where(SupplierLedgerEntry.purchase_id == purchase.id)
        )
    ).all()
    if not entries or any(
        entry.kind != "purchase" or entry.supplier_id != purchase.supplier_id for entry in entries
    ):
        raise ValueError("The supplier ledger for this purchase could not be verified")
    for entry in entries:
        db.add(
            SupplierLedgerEntry(
                supplier_id=entry.supplier_id,
                purchase_id=purchase.id,
                purity_id=entry.purity_id,
                gold_24k=-entry.gold_24k,
                valuation_factor=entry.valuation_factor,
                gold_grams=-entry.gold_grams,
                making_usd=-entry.making_usd,
                reversal_of_id=entry.id,
                source_key=f"purchase-void:{entry.id}",
                kind="reversal",
                note=reason,
                created_by=user_id,
            )
        )
    for item in items:
        item.status = "voided"
        db.add(
            InventoryMovement(
                inventory_item_id=item.id,
                movement_type="purchase_void",
                from_location_id=item.location_id,
                created_by=user_id,
            )
        )


async def void_bulk_purchase(db: AsyncSession, purchase: Purchase, reason: str, user_id: int):
    await db.scalar(
        select(Location.id).where(Location.id == purchase.location_id).with_for_update()
    )
    stock = await db.scalar(select(PurchaseStock).where(PurchaseStock.purchase_id == purchase.id))
    if stock is None or stock.credited_balance_id is None or purchase.paid_usd is None:
        raise ValueError("The original stock credit for this purchase could not be verified")
    balance = await db.scalar(
        select(InventoryBalance)
        .where(InventoryBalance.id == stock.credited_balance_id)
        .with_for_update()
    )
    if (
        balance is None
        or balance.location_id != purchase.location_id
        or balance.placement != stock.stock_for
        or balance.updated_at != stock.credited_balance_updated_at
        or balance.total_weight < stock.weight
        or balance.cost_usd is None
        or balance.cost_usd < purchase.paid_usd
        or (balance.total_weight == stock.weight and balance.cost_usd != purchase.paid_usd)
    ):
        raise ValueError("The original stock balance has changed or its cost is unavailable")
    if purchase.paid_usd:
        cash = await db.scalar(select(CashEntry).where(CashEntry.purchase_id == purchase.id))
        if (
            cash is None
            or cash.kind != "customer_purchase"
            or cash.location_id != purchase.location_id
            or cash.amount_usd != -purchase.paid_usd
        ):
            raise ValueError("The original cash payment for this purchase could not be verified")
    await change_stock(
        db,
        unit=active_unit(),
        location_id=purchase.location_id,
        purity_id=balance.purity_id,
        placement=balance.placement,
        delta=-stock.weight,
        value=purchase.paid_usd,
    )
    doc = await document(
        db,
        unit=active_unit(),
        kind="purchase_void",
        location_id=purchase.location_id,
        user_id=user_id,
        note=reason,
        amount=purchase.paid_usd,
        details={"purchase_id": purchase.id},
    )
    cash_entry(db, doc, active_unit(), purchase.location_id, purchase.paid_usd, "adjustment")


async def void_purchase(db: AsyncSession, purchase_id: int, reason: str, user_id: int) -> Purchase:
    purchase = await locked_purchase(db, purchase_id)
    if purchase.voided_at is not None:
        return purchase
    try:
        if purchase.source == "supplier":
            await void_item_invoice(db, purchase, reason, user_id)
        elif purchase.source in {"customer", "opening"}:
            await void_bulk_purchase(db, purchase, reason, user_id)
        else:
            raise ValueError("This purchase source does not support voiding")
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    purchase.voided_at = await db.scalar(select(func.now()))
    purchase.voided_by = user_id
    purchase.void_reason = reason
    await db.commit()
    return purchase
