"""Recorded-cost margins; internal revenue is excluded from company results."""

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.core.config import settings
from app.core.workspace import in_workspace
from app.models import CashEntry, InventoryItem, ItemReturn, PurchaseItem, Sale, SaleItem, SaleStock
from app.models.operations import InternalInvoice, ProductionPiece

ZERO = Decimal(0)


def money(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def bounds(month):
    year, number = map(int, month.split("-"))
    zone = ZoneInfo(settings.report_timezone)
    return datetime(year, number, 1, tzinfo=zone).astimezone(UTC), datetime(
        year + (number == 12), number % 12 + 1, 1, tzinfo=zone
    ).astimezone(UTC)


def legacy_cost(purchase, produced):
    if purchase is not None:
        return purchase.weight * purchase.gold_price_per_gram + purchase.making_charge
    return produced.total_cost_usd if produced is not None else None


async def unit_report(db, unit, start, end, location_id=None, *, company=False):
    with in_workspace(unit):
        sales = (
            select(SaleItem, Sale, PurchaseItem, ProductionPiece)
            .join(Sale, Sale.id == SaleItem.sale_id)
            .join(InventoryItem, InventoryItem.id == SaleItem.inventory_item_id)
            .outerjoin(PurchaseItem, PurchaseItem.id == InventoryItem.purchase_item_id)
            .outerjoin(ProductionPiece, ProductionPiece.id == InventoryItem.production_piece_id)
            .where(Sale.created_at >= start, Sale.created_at < end)
        )
        returns = (
            select(ItemReturn, SaleItem, Sale, PurchaseItem, ProductionPiece)
            .join(SaleItem, SaleItem.id == ItemReturn.sale_item_id)
            .join(Sale, Sale.id == SaleItem.sale_id)
            .join(InventoryItem, InventoryItem.id == SaleItem.inventory_item_id)
            .outerjoin(PurchaseItem, PurchaseItem.id == InventoryItem.purchase_item_id)
            .outerjoin(ProductionPiece, ProductionPiece.id == InventoryItem.production_piece_id)
            .where(ItemReturn.created_at >= start, ItemReturn.created_at < end)
        )
        bulk = (
            select(SaleStock)
            .join(Sale, Sale.id == SaleStock.sale_id)
            .where(Sale.created_at >= start, Sale.created_at < end)
        )
        expenses = select(func.coalesce(-func.sum(CashEntry.amount_usd), 0)).where(
            CashEntry.kind == "expense", CashEntry.created_at >= start, CashEntry.created_at < end
        )
        if location_id:
            sales = sales.where(Sale.location_id == location_id)
            returns = returns.where(Sale.location_id == location_id)
            bulk = bulk.where(Sale.location_id == location_id)
            expenses = expenses.where(CashEntry.location_id == location_id)
        revenue, cost, refunds, restored, unknown, count = ZERO, ZERO, ZERO, ZERO, 0, 0
        for line, _sale, purchase, produced in await db.execute(sales):
            revenue += line.sell_price
            value = line.company_cost_usd if company else line.cost_usd
            if value is None:
                value = legacy_cost(purchase, produced)
            if value is None:
                unknown += 1
            else:
                cost += value
            count += 1
        for returned, line, _sale, purchase, produced in await db.execute(returns):
            refunds += returned.refund_usd
            value = line.company_cost_usd if company else line.cost_usd
            if value is None:
                value = legacy_cost(purchase, produced)
            if value is None:
                unknown += 1
            else:
                restored += value
        for line in await db.scalars(bulk):
            if line.gold_price_per_gram is None or line.cost_usd is None:
                unknown += 1
            else:
                revenue += line.gold_charge_in_grams * line.gold_price_per_gram + line.making_charge
                cost += line.cost_usd
            count += 1
        expense = await db.scalar(expenses)
    internal_revenue, internal_cost = ZERO, ZERO
    if unit == "factory" and not company:
        statement = select(
            func.coalesce(func.sum(InternalInvoice.total_value_usd), 0),
            func.coalesce(func.sum(InternalInvoice.factory_cost_usd), 0),
        ).where(InternalInvoice.created_at >= start, InternalInvoice.created_at < end)
        if location_id:
            statement = statement.where(InternalInvoice.factory_location_id == location_id)
        internal_revenue, internal_cost = (await db.execute(statement)).one()
    total_revenue = revenue - refunds + internal_revenue
    total_cost = cost - restored + internal_cost
    return {
        "unit": unit,
        "external_sales_usd": money(revenue),
        "refunds_usd": money(refunds),
        "internal_sales_usd": money(internal_revenue),
        "revenue_usd": money(total_revenue),
        "cost_of_sales_usd": money(total_cost),
        "expenses_usd": money(expense),
        "profit_usd": None if unknown else money(total_revenue - total_cost - expense),
        "uncosted_trades": unknown,
        "sales_count": count,
    }


async def profit_report(db, month, unit, location_id=None):
    start, end = bounds(month)
    if unit != "company":
        result = await unit_report(db, unit, start, end, location_id)
    else:
        rows = [
            await unit_report(db, name, start, end, location_id, company=True)
            for name in ["factory", "showroom"]
        ]
        result = {
            "unit": "company",
            **{
                key: sum((row[key] for row in rows), ZERO)
                for key in [
                    "external_sales_usd",
                    "refunds_usd",
                    "internal_sales_usd",
                    "revenue_usd",
                    "cost_of_sales_usd",
                    "expenses_usd",
                    "sales_count",
                    "uncosted_trades",
                ]
            },
        }
        result["profit_usd"] = (
            None if result["uncosted_trades"] else sum((row["profit_usd"] for row in rows), ZERO)
        )
    return {
        **result,
        "month": month,
        "timezone": settings.report_timezone,
        "cost_method": (
            "Recorded acquisition / production cost; company report excludes internal trade"
        ),
    }
