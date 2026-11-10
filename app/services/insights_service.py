from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Location
from app.models.cashLedger import CashEntry
from app.models.inventoryItem import InventoryItem
from app.models.itemReturn import ItemReturn
from app.models.purchase import Purchase
from app.models.purchaseItem import PurchaseItem
from app.models.saleItem import SaleItem
from app.models.sales import Sale
from app.models.saleStock import SaleStock
from app.models.supplierLedger import SupplierLedgerEntry


async def monthly_profit_service(
    db: AsyncSession,
    month: str,
    location_id: int | None = None,
) -> dict[str, object]:
    zone = ZoneInfo(settings.report_timezone)
    try:
        year, number = map(int, month.split("-"))
        start = datetime(year, number, 1, tzinfo=zone).astimezone(UTC)
        end = datetime(year + (number == 12), number % 12 + 1, 1, tzinfo=zone).astimezone(UTC)
    except ValueError as error:
        raise HTTPException(422, "Invalid reporting month") from error
    if location_id is not None and await db.get(Location, location_id) is None:
        raise HTTPException(404, "Location not found")

    # Supplier gold liability is recorded in grams, valued at THIS sale's price.
    # Reversing a return uses its original sale valuation, including on resale.
    gold = PurchaseItem.gold_charge_in_grams * SaleItem.gold_price_per_gram
    making = PurchaseItem.weight * PurchaseItem.making_charge
    sold = (
        select(
            func.count(SaleItem.id).label("sold_count"),
            func.coalesce(func.sum(SaleItem.sell_price), 0).label("sales"),
            func.coalesce(func.sum(gold), 0).label("gold"),
            func.coalesce(func.sum(making), 0).label("making"),
        )
        .select_from(SaleItem)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .join(InventoryItem, InventoryItem.id == SaleItem.inventory_item_id)
        .join(PurchaseItem, PurchaseItem.id == InventoryItem.purchase_item_id)
        .where(Sale.created_at >= start, Sale.created_at < end, Sale.kind == "customer")
    )
    returns = (
        select(
            func.count(ItemReturn.id).label("returned_count"),
            func.coalesce(func.sum(ItemReturn.refund_usd), 0).label("refunds"),
            func.coalesce(func.sum(gold + making), 0).label("restored"),
        )
        .select_from(ItemReturn)
        .join(SaleItem, SaleItem.id == ItemReturn.sale_item_id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .join(InventoryItem, InventoryItem.id == SaleItem.inventory_item_id)
        .join(PurchaseItem, PurchaseItem.id == InventoryItem.purchase_item_id)
        .where(ItemReturn.created_at >= start, ItemReturn.created_at < end, Sale.kind == "customer")
    )
    expenses = select(func.coalesce(-func.sum(CashEntry.amount_usd), 0)).where(
        CashEntry.kind == "expense", CashEntry.created_at >= start, CashEntry.created_at < end
    )
    supplier = (
        select(
            SaleStock.gold_purity_id.label("purity_id"),
            func.sum(SaleStock.weight).label("weight_grams"),
            func.sum(SaleStock.gold_charge_in_grams).label("settlement_grams"),
            func.sum(SaleStock.making_charge).label("making_usd"),
        )
        .join(Sale, Sale.id == SaleStock.sale_id)
        .where(Sale.created_at >= start, Sale.created_at < end)
        .group_by(SaleStock.gold_purity_id)
        .order_by(SaleStock.gold_purity_id)
    )
    supplier_purchases = (
        select(
            SupplierLedgerEntry.purity_id,
            func.sum(SupplierLedgerEntry.gold_grams).label("gold_grams"),
            func.sum(SupplierLedgerEntry.making_usd).label("making_usd"),
        )
        .join(Purchase, Purchase.id == SupplierLedgerEntry.purchase_id)
        .where(
            SupplierLedgerEntry.kind == "purchase",
            Purchase.created_at >= start,
            Purchase.created_at < end,
        )
        .group_by(SupplierLedgerEntry.purity_id)
        .order_by(SupplierLedgerEntry.purity_id)
    )
    if location_id is not None:
        sold = sold.where(Sale.location_id == location_id)
        # Attribute a return to the original sale location for margin reporting.
        returns = returns.where(Sale.location_id == location_id)
        expenses = expenses.where(CashEntry.location_id == location_id)
        supplier = supplier.where(Sale.location_id == location_id)
        supplier_purchases = supplier_purchases.where(Purchase.location_id == location_id)
    sold, returns = sold.subquery(), returns.subquery()
    # One statement provides a consistent snapshot for all customer profit totals.
    row = (
        (
            await db.execute(
                select(sold, returns, expenses.scalar_subquery().label("expenses"))
                .select_from(sold)
                .join(returns, true())
            )
        )
        .mappings()
        .one()
    )

    def money(value):
        return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    revenue, refunded = money(row["sales"]), money(row["refunds"])
    gold_value, making, restored = map(money, (row["gold"], row["making"], row["restored"]))
    cost = gold_value + making - restored
    gross = revenue - refunded - cost
    expense = money(row["expenses"])
    return dict(
        month=month,
        timezone=settings.report_timezone,
        location_id=location_id,
        customer_sales_count=row["sold_count"],
        returned_items_count=row["returned_count"],
        sales_usd=revenue,
        refunds_usd=refunded,
        net_sales_usd=revenue - refunded,
        gold_value_usd=gold_value,
        making_cost_usd=making,
        restored_cost_usd=restored,
        net_cost_usd=cost,
        gross_profit_usd=gross,
        expenses_usd=expense,
        net_profit_usd=gross - expense,
        supplier_sales=(await db.execute(supplier)).mappings().all(),
        supplier_purchases=(await db.execute(supplier_purchases)).mappings().all(),
    )
