from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import Purchase, PurchaseItem, Sale, SaleItem
from app.models.cashLedger import CashEntry
from app.models.itemReturn import ItemReturn
from tests.api.test_backend_access import headers_for
from tests.api.test_locations import test_create_location as make_location
from tests.api.test_purchase import test_create_purchase as make_purchase
from tests.api.test_sale import test_create_sale_stock as make_bulk_sale

pytestmark = pytest.mark.asyncio(loop_scope="session")
URL = "/api/v1/insights/monthly-profit"


async def customer_sale(client, factory):
    purchase, _, inventory = await make_purchase(client, factory)
    async with factory() as db:
        line = await db.scalar(
            select(PurchaseItem).where(PurchaseItem.purchase_id == purchase.json()["id"])
        )
        line.gold_charge_in_grams = Decimal("2")
        line.gold_price_per_gram = Decimal("10")  # Must not use historical gold price.
        line.making_charge = Decimal("5")
        await db.commit()
    payload = {
        "location_id": purchase.json()["location_id"],
        "items": [
            {
                "inventory_item_id": inventory.json()["id"],
                "gold_price_per_gram": "80",
                "discount": "50",
                "sell_price": "200",
            }
        ],
    }
    result = await client.post("/api/v1/sales/item", json=payload)
    assert result.status_code == 201
    async with factory() as db:
        sale = await db.get(Sale, result.json()["id"])
        sale.created_at = datetime(2026, 4, 15, tzinfo=UTC)
        await db.commit()
    return sale, inventory.json()["id"]


async def outflow(client, factory, location, kind, amount, at):
    result = await client.post(
        "/api/v1/cash/outflows",
        json={
            "location_id": location,
            "kind": kind,
            "amount_usd": amount,
            "description": "Report test",
        },
        headers={"Idempotency-Key": f"{kind}-{location}-{amount}"},
    )
    assert result.status_code == 201
    async with factory() as db:
        entry = await db.get(CashEntry, result.json()["id"])
        entry.created_at = at
        await db.commit()


async def test_monthly_sale_price_margin_and_expenses(client, test_session_factory):
    sale, _ = await customer_sale(client, test_session_factory)
    await outflow(
        client,
        test_session_factory,
        sale.location_id,
        "expense",
        "12.50",
        datetime(2026, 4, 20, tzinfo=UTC),
    )
    await outflow(
        client,
        test_session_factory,
        sale.location_id,
        "withdrawal",
        "40",
        datetime(2026, 4, 20, tzinfo=UTC),
    )
    response = await client.get(URL, params={"month": "2026-04"})
    assert response.status_code == 200, response.text
    report = response.json()
    for key, expected in {
        "sales_usd": 200,
        "gold_value_usd": 160,
        "making_cost_usd": 5,
        "gross_profit_usd": 35,
        "expenses_usd": "12.50",
        "net_profit_usd": "22.50",
    }.items():
        assert Decimal(report[key]) == Decimal(str(expected)), (key, report)
    assert report["customer_sales_count"] == 1
    assert report["returned_items_count"] == 0
    # One location and all locations agree; another location has no business.
    filtered = (
        await client.get(URL, params={"month": "2026-04", "location_id": sale.location_id})
    ).json()
    assert filtered["net_profit_usd"] == report["net_profit_usd"]
    other = (await make_location(client)).json()["id"]
    assert (
        Decimal(
            (await client.get(URL, params={"month": "2026-04", "location_id": other})).json()[
                "net_profit_usd"
            ]
        )
        == 0
    )


async def test_returns_and_resale_are_accounted_in_their_own_month(client, test_session_factory):
    sale, inventory_id = await customer_sale(client, test_session_factory)
    other = (await make_location(client)).json()["id"]
    async with test_session_factory() as db:
        line = await db.scalar(select(SaleItem).where(SaleItem.sale_id == sale.id))
        line_id = line.id
    result = await client.post(
        "/api/v1/inventory/returns",
        json={"sale_item_id": line_id, "location_id": other, "refund_usd": "180"},
    )
    assert result.status_code == 201
    async with test_session_factory() as db:
        returned = await db.get(ItemReturn, result.json()["id"])
        returned.created_at = datetime(2026, 5, 5, tzinfo=UTC)
        await db.commit()
    # A return belongs to the original sale location, even if received elsewhere.
    may = (
        await client.get(URL, params={"month": "2026-05", "location_id": sale.location_id})
    ).json()
    assert Decimal(may["refunds_usd"]) == 180
    assert Decimal(may["restored_cost_usd"]) == 165
    assert Decimal(may["net_profit_usd"]) == -15
    april = (await client.get(URL, params={"month": "2026-04"})).json()
    assert Decimal(april["net_profit_usd"]) == 35
    result = await client.post(
        "/api/v1/sales/item",
        json={
            "location_id": other,
            "items": [
                {
                    "inventory_item_id": inventory_id,
                    "gold_price_per_gram": "90",
                    "discount": "0",
                    "sell_price": "220",
                }
            ],
        },
    )
    assert result.status_code == 201
    async with test_session_factory() as db:
        resale = await db.get(Sale, result.json()["id"])
        resale.created_at = datetime(2026, 5, 10, tzinfo=UTC)
        await db.commit()
    may = (await client.get(URL, params={"month": "2026-05"})).json()
    assert may["customer_sales_count"] == may["returned_items_count"] == 1
    assert Decimal(may["net_cost_usd"]) == 20  # 185 cost less 165 restored.
    assert Decimal(may["net_profit_usd"]) == 20  # 220 - 180 - 20.


async def test_calendar_timezone_boundaries_and_invalid_month(
    client, test_session_factory, monkeypatch
):
    monkeypatch.setattr(settings, "report_timezone", "Asia/Beirut")
    sale, _ = await customer_sale(client, test_session_factory)
    async with test_session_factory() as db:
        row = await db.get(Sale, sale.id)
        row.created_at = datetime(2026, 3, 31, 21, tzinfo=UTC)  # April 1 in Beirut.
        await db.commit()
    await outflow(
        client,
        test_session_factory,
        sale.location_id,
        "expense",
        "10",
        datetime(2026, 4, 30, 21, tzinfo=UTC),
    )  # May 1, excluded from April.
    april = (await client.get(URL, params={"month": "2026-04"})).json()
    assert april["timezone"] == "Asia/Beirut"
    assert Decimal(april["net_profit_usd"]) == 35
    assert (
        Decimal((await client.get(URL, params={"month": "2026-05"})).json()["net_profit_usd"])
        == -10
    )
    assert (
        Decimal((await client.get(URL, params={"month": "2026-12"})).json()["net_profit_usd"]) == 0
    )
    for month in ["2026-13", "2026-00", "0000-01", "9999-12", "nonsense"]:
        assert (await client.get(URL, params={"month": month})).status_code == 422
    assert (
        await client.get(URL, params={"month": "2026-04", "location_id": 2147483647})
    ).status_code == 404


async def test_supplier_trades_stay_separate_from_customer_profit(client, test_session_factory):
    await make_bulk_sale(client, test_session_factory)
    async with test_session_factory() as db:
        for sale in (await db.scalars(select(Sale))).all():
            sale.created_at = datetime(2026, 4, 10, tzinfo=UTC)
        for purchase in (await db.scalars(select(Purchase))).all():
            purchase.created_at = datetime(2026, 4, 5, tzinfo=UTC)
        await db.commit()
    report = (await client.get(URL, params={"month": "2026-04"})).json()
    assert Decimal(report["net_profit_usd"]) == 0
    assert report["customer_sales_count"] == 0
    assert Decimal(report["supplier_sales"][0]["weight_grams"]) == Decimal("1.600")
    assert Decimal(report["supplier_sales"][0]["making_usd"]) == Decimal("3.50")
    assert Decimal(report["supplier_purchases"][0]["gold_grams"]) == Decimal("2.600")


@pytest.mark.parametrize("role", ["cashier", "employee"])
async def test_profit_insights_are_admin_only(client, test_session_factory, role):
    headers = await headers_for(test_session_factory, role)
    assert (await client.get(URL, params={"month": "2026-04"}, headers=headers)).status_code == 403
    assert (
        await client.get(URL, params={"month": "2026-04"}, headers={"Authorization": ""})
    ).status_code == 401
