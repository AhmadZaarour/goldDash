"""Per-gram making rates become total USD debt and permanent piece costs."""

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.models import InventoryItem, SaleItem, SupplierLedgerEntry
from tests.api.test_workspaces import header, shop

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def report(client, path="operations/profit"):
    month = datetime.now(ZoneInfo("Asia/Beirut")).strftime("%Y-%m")
    response = await client.get(f"/api/v1/{path}", params={"month": month})
    assert response.status_code == 200, response.text
    return response.json()


async def buy(client, s, lines, key="per-gram-purchase"):
    response = await client.post(
        "/api/v1/purchases/item",
        json={
            "supplier_id": s["supplier"],
            "location_id": s["location"],
            "total_gold_charge_grams": str(sum((Decimal(w) for w, _ in lines), Decimal(0))),
            "items": [
                {
                    "supplier_id": s["supplier"],
                    "product_id": s["item"],
                    "weight": w,
                    "making_charge": rate,
                }
                for w, rate in lines
            ],
        },
        headers=header("showroom", key),
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize("legacy", [False, True])
async def test_purchase_debt_sale_cost_and_return_use_physical_weight(
    client, test_session_factory, legacy
):
    s = await shop(test_session_factory)
    lines = [("5", "10"), ("2", "3")]
    purchase = await buy(client, s, lines)
    replay = await buy(client, s, lines)
    assert replay == purchase
    balance_url = f"/api/v1/suppliers/{s['supplier']}/balance"
    balance = (await client.get(balance_url)).json()
    assert Decimal(balance["making_usd"]) == 56
    # Independent Factory account has no making debt.
    factory_balance = (await client.get(balance_url, headers=header("factory"))).json()
    assert Decimal(factory_balance["making_usd"]) == 0
    inventory = (
        await client.get("/api/v1/inventory/items", params={"purchase_id": purchase["id"]})
    ).json()
    item = next(row for row in inventory if Decimal(row["weight"]) == 5)
    # 18K quote = 75.7538/g, making = 10/g: 5 * 85.7538.
    assert Decimal(item["base_cost_usd"]) == Decimal("428.77")
    if legacy:
        async with test_session_factory() as db:
            original = await db.get(InventoryItem, item["id"])
            original.owner_cost_usd = original.company_cost_usd = None
            await db.commit()
        assert Decimal(
            (await client.get(f"/api/v1/inventory/items/{item['id']}")).json()["base_cost_usd"]
        ) == Decimal("428.77")
    sale = await client.post(
        "/api/v1/sales/item",
        json={
            "location_id": s["location"],
            "items": [{"inventory_item_id": item["id"], "sell_price": "600", "discount": "0"}],
        },
    )
    assert sale.status_code == 201, sale.text
    if legacy:
        # Historical sales without saved costs must use the same per-gram fallback.
        async with test_session_factory() as db:
            line = await db.scalar(select(SaleItem).where(SaleItem.sale_id == sale.json()["id"]))
            line.cost_usd = line.company_cost_usd = None
            await db.commit()
    assert Decimal((await report(client))["profit_usd"]) == Decimal("171.23")
    margin = await report(client, "insights/monthly-profit")
    assert Decimal(margin["making_cost_usd"]) == 50
    assert Decimal(margin["net_profit_usd"]) == Decimal("171.23")
    settlement = await client.post(
        f"/api/v1/suppliers/{s['supplier']}/settlements",
        json={
            "idempotency_key": "pay-making",
            "direction": "sent",
            "location_id": s["location"],
            "making_usd": "56",
        },
    )
    assert settlement.status_code == 201, settlement.text
    assert Decimal(settlement.json()["making_usd"]) == 0
    async with test_session_factory() as db:
        posted = await db.scalar(
            select(SupplierLedgerEntry).where(SupplierLedgerEntry.purchase_id == purchase["id"])
        )
        assert posted.making_usd == 56
    line = (await client.get(f"/api/v1/sales/item/{sale.json()['id']}")).json()[0]
    returned = await client.post(
        "/api/v1/inventory/returns",
        json={"sale_item_id": line["id"], "location_id": s["location"], "refund_usd": "500"},
    )
    assert returned.status_code == 201, returned.text
    assert Decimal((await report(client))["profit_usd"]) == 100
    margin = await report(client, "insights/monthly-profit")
    assert Decimal(margin["restored_cost_usd"]) == Decimal("428.77")
    assert Decimal(margin["net_profit_usd"]) == 100


async def test_invoice_making_debt_rounds_once_after_weighting_each_line(
    client, test_session_factory
):
    s = await shop(test_session_factory)
    await buy(client, s, [("0.333", "0.01"), ("0.333", "0.01")])
    balance = (await client.get(f"/api/v1/suppliers/{s['supplier']}/balance")).json()
    # 0.00333 + 0.00333 = 0.00666, rounded once to $0.01.
    assert Decimal(balance["making_usd"]) == Decimal("0.01")
