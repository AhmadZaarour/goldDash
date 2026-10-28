from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import InventoryItem, ItemReturn
from app.models.cashLedger import CashEntry
from tests.api.test_purchase import test_create_purchase as create_purchase

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_cash_sale_refund_and_reconciliation(client, test_session_factory):
    purchase, _, item_response = await create_purchase(client, test_session_factory)
    item_id = item_response.json()["id"]
    location_id = purchase.json()["location_id"]
    payload = {
        "location_id": location_id,
        "items": [
            {
                "inventory_item_id": item_id,
                "gold_price_per_gram": "100",
                "discount": "5",
                "sell_price": "125.25",
            }
        ],
    }
    response = await client.post("/api/v1/sales/item", json=payload)
    assert response.status_code == 201, response.text
    sale_id = response.json()["id"]
    # sell_price is final; the discount is not subtracted a second time.
    summary = (await client.get("/api/v1/cash/summary", params={"location_id": location_id})).json()
    assert Decimal(summary["net_usd"]) == Decimal("125.25")
    entries = await client.get("/api/v1/cash/entries", params={"location_id": location_id})
    assert entries.status_code == 200
    assert entries.headers["X-Total-Count"] == "1"
    assert entries.json()[0]["sale_id"] == sale_id
    assert Decimal(entries.json()[0]["amount_usd"]) == Decimal("125.25")
    duplicate = await client.post("/api/v1/sales/item", json=payload)
    assert duplicate.status_code == 409
    lines = (await client.get(f"/api/v1/sales/item/{sale_id}")).json()
    refund = {"sale_item_id": lines[0]["id"], "location_id": location_id, "refund_usd": "100.00"}
    returned = await client.post("/api/v1/inventory/returns", json=refund)
    assert returned.status_code == 201, returned.text
    assert (await client.post("/api/v1/inventory/returns", json=refund)).status_code == 409
    summary = (await client.get("/api/v1/cash/summary", params={"location_id": location_id})).json()
    assert Decimal(summary["received_usd"]) == Decimal("125.25")
    assert Decimal(summary["refunded_usd"]) == Decimal("100.00")
    assert Decimal(summary["net_usd"]) == Decimal("25.25")
    now = datetime.now(UTC)
    reconciliation = {
        "idempotency_key": "cash-close",
        "location_id": location_id,
        "from_at": (now - timedelta(days=1)).isoformat(),
        "to_at": now.isoformat(),
        "opening_usd": "10",
        "counted_usd": "35.00",
    }
    response = await client.post("/api/v1/cash/reconciliations", json=reconciliation)
    assert response.status_code == 201, response.text
    assert Decimal(response.json()["expected_usd"]) == Decimal("35.25")
    assert Decimal(response.json()["variance_usd"]) == Decimal("-0.25")
    assert (
        await client.post("/api/v1/cash/reconciliations", json=reconciliation)
    ).status_code == 409
    assert (
        await client.get("/api/v1/cash/reconciliations", params={"location_id": location_id})
    ).json() == [response.json()]
    async with test_session_factory() as db:
        entries = list(await db.scalars(select(CashEntry)))
        assert len(entries) == 2
        assert (await db.get(InventoryItem, item_id)).status == "in_stock"
        assert await db.get(ItemReturn, returned.json()["id"]) is not None


async def test_failed_sale_does_not_create_cash_receipt(client, test_session_factory):
    purchase, _, item = await create_purchase(client, test_session_factory)
    payload = {
        "location_id": purchase.json()["location_id"],
        "items": [
            {
                "inventory_item_id": item.json()["id"],
                "gold_price_per_gram": 100,
                "discount": 0,
                "sell_price": 100,
            },
            {
                "inventory_item_id": 2147483647,
                "gold_price_per_gram": 100,
                "discount": 0,
                "sell_price": 100,
            },
        ],
    }
    assert (await client.post("/api/v1/sales/item", json=payload)).status_code == 409
    async with test_session_factory() as db:
        assert list(await db.scalars(select(CashEntry))) == []
        assert (await db.get(InventoryItem, item.json()["id"])).status == "in_stock"


async def test_cashier_can_sell_but_cannot_reconcile(client, test_session_factory):
    from tests.api.test_backend_access import headers_for

    purchase, _, item = await create_purchase(client, test_session_factory)
    headers = await headers_for(test_session_factory, "cashier")
    response = await client.post(
        "/api/v1/sales/item",
        headers=headers,
        json={
            "location_id": purchase.json()["location_id"],
            "items": [
                {
                    "inventory_item_id": item.json()["id"],
                    "gold_price_per_gram": 100,
                    "discount": 0,
                    "sell_price": "50.00",
                }
            ],
        },
    )
    assert response.status_code == 201, response.text
    assert (
        await client.post("/api/v1/cash/reconciliations", json={}, headers=headers)
    ).status_code == 403
    summary = await client.get(
        "/api/v1/cash/summary",
        params={"location_id": purchase.json()["location_id"]},
        headers=headers,
    )
    assert summary.status_code == 200
    assert Decimal(summary.json()["net_usd"]) == 50
