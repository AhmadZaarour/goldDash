from decimal import Decimal
from pydantic.v1 import BaseModel


class SupplierTrade(BaseModel):
    purity_id: int
    weight_grams: Decimal
    settlement_grams: Decimal
    making_usd: Decimal


class SupplierPurchase(BaseModel):
    purity_id: int
    gold_grams: Decimal
    making_usd: Decimal


class MonthlyProfit(BaseModel):
    month: str
    timezone: str
    location_id: int | None
    customer_sales_count: int
    returned_items_count: int
    sales_usd: Decimal
    refunds_usd: Decimal
    net_sales_usd: Decimal
    gold_value_usd: Decimal
    making_cost_usd: Decimal
    restored_cost_usd: Decimal
    net_cost_usd: Decimal
    gross_profit_usd: Decimal
    expenses_usd: Decimal
    net_profit_usd: Decimal
    supplier_sales: list[SupplierTrade]
    supplier_purchases: list[SupplierPurchase]