"""Market rates are snapshots; actual cash and supplier obligations remain explicit."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.models import InventoryBalance, InventoryItem, Purchase, Sale, SupplierLedgerEntry
from app.models.cashLedger import CashEntry
from app.models.purchaseStock import PurchaseStock
from app.services import purchase_service, sale_service
from tests.api.test_gold_workflows import invoice, setup_shop

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.mark.parametrize("paid", ["0", "250"])
async def test_bulk_acquisition_records_market_rate_separately_from_paid_cost(
    client, test_session_factory, monkeypatch, paid
):
    s = await setup_shop(client, test_session_factory)
    calls = []
    timestamp = datetime.now(UTC).isoformat()

    async def quote():
        calls.append(True)
        return {"gram_24k_usd": "100.5", "fetched_at": timestamp, "stale": False}

    monkeypatch.setattr(purchase_service, "get_quote", quote)
    body = {
        "location_id": s["location"],
        "product_id": s["bulk"],
        "weight": "5",
        "paid_usd": paid,
        "gold_price_per_gram": "1",
    }
    headers = {"Idempotency-Key": "bulk-price"}
    results = await asyncio.gather(
        *[
            client.post("/api/v1/purchases/customer-stock", json=body, headers=headers)
            for _ in range(2)
        ]
    )
    assert [r.status_code for r in results] == [201, 201]
    assert results[0].json() == results[1].json()
    assert len(calls) == 1
    purchase = results[0].json()
    assert Decimal(purchase["paid_usd"]) == Decimal(paid)
    assert datetime.fromisoformat(
        purchase["gold_quote_at"].replace("Z", "+00:00")
    ) == datetime.fromisoformat(timestamp)
    stock = (await client.get(f"/api/v1/purchases/stock/{purchase['id']}")).json()
    assert Decimal(stock["gold_price_per_gram"]) == Decimal("75.7538")
    assert Decimal(stock["cost_per_gram"]) == Decimal(paid) / 5
    async with test_session_factory() as db:
        assert await db.scalar(select(func.sum(CashEntry.amount_usd))) == 1000 - Decimal(paid)
        assert await db.scalar(select(func.count()).select_from(SupplierLedgerEntry)) == 0

    async def unavailable():
        raise HTTPException(503, "No quote")

    monkeypatch.setattr(purchase_service, "get_quote", unavailable)
    assert (
        await client.post("/api/v1/purchases/customer-stock", json=body, headers=headers)
    ).json() == purchase
    assert (await client.get(f"/api/v1/purchases/stock/{purchase['id']}")).json() == stock


async def test_customer_sale_uses_one_quote_for_mixed_karats_and_keeps_cash_manual(
    client, test_session_factory, monkeypatch, purchase_market_quote
):
    s = await setup_shop(client, test_session_factory)
    purchase = await client.post("/api/v1/purchases/item", json=invoice(s))
    items = (
        await client.get("/api/v1/inventory/items", params={"purchase_id": purchase.json()["id"]})
    ).json()
    calls = []

    async def quote():
        calls.append(True)
        return {"gram_24k_usd": "200", "fetched_at": datetime.now(UTC).isoformat(), "stale": False}

    monkeypatch.setattr(sale_service, "get_quote", quote)
    result = await client.post(
        "/api/v1/sales/item",
        json={
            "location_id": s["location"],
            "items": [
                {
                    "inventory_item_id": item["id"],
                    "discount": "5",
                    "sell_price": price,
                    "gold_price_per_gram": "0",
                }
                for item, price in zip(items, ["125", "175"], strict=True)
            ],
        },
    )
    assert result.status_code == 201, result.text
    assert result.json()["gold_quote_at"]
    lines = (await client.get(f"/api/v1/sales/item/{result.json()['id']}")).json()
    assert [Decimal(line["gold_price_per_gram"]) for line in lines] == [
        Decimal("150.7538"),
        Decimal("175.8794"),
    ]
    assert [Decimal(line["sell_price"]) for line in lines] == [125, 175]
    assert len(calls) == 1
    async with test_session_factory() as db:
        assert await db.scalar(select(func.sum(CashEntry.amount_usd))) == 1300
        assert (
            await db.scalar(
                select(func.count())
                .select_from(InventoryItem)
                .where(InventoryItem.status == "sold")
            )
            == 2
        )
    purchase_market_quote["gram_24k_usd"] = "500"
    assert (await client.get(f"/api/v1/sales/item/{result.json()['id']}")).json() == lines


@pytest.mark.parametrize(
    "purity,expected", [("p18", "75.7538"), ("p21", "88.3794"), ("p24", "100.5000")]
)
async def test_supplier_bulk_sale_records_rate_without_turning_it_into_cash(
    client, test_session_factory, purity, expected
):
    s = await setup_shop(client, test_session_factory)
    if purity == "p24":
        async with test_session_factory() as db:
            db.add(
                InventoryBalance(
                    purity_id=s[purity],
                    location_id=s["location"],
                    placement="factory",
                    total_weight=100,
                )
            )
            await db.commit()
    result = await client.post(
        "/api/v1/sales/stock",
        json={
            "location_id": s["location"],
            "item": {
                "supplier_id": s["supplier"],
                "gold_purity_id": s[purity],
                "weight": "2",
                "gold_charge_in_grams": "2",
                "making_charge": "3.5",
            },
        },
    )
    assert result.status_code == 201, result.text
    assert result.json()["gold_quote_at"]
    stock = (await client.get(f"/api/v1/sales/stock/{result.json()['id']}")).json()
    assert Decimal(stock["gold_price_per_gram"]) == Decimal(expected)
    async with test_session_factory() as db:
        assert await db.scalar(select(func.sum(CashEntry.amount_usd))) == 1000
        assert (
            await db.scalar(
                select(InventoryBalance.total_weight).where(InventoryBalance.purity_id == s[purity])
            )
            == 98
        )
        entry = await db.scalar(select(SupplierLedgerEntry))
        assert entry.making_usd == Decimal("-3.5")


@pytest.mark.parametrize("flow", ["bulk_purchase", "item_sale", "bulk_sale"])
@pytest.mark.parametrize("failure", ["stale", "unavailable"])
async def test_unavailable_quotes_cannot_partially_post_any_trade(
    client, test_session_factory, monkeypatch, flow, failure
):
    s = await setup_shop(client, test_session_factory)
    await client.post("/api/v1/purchases/item", json=invoice(s))
    items = (await client.get("/api/v1/inventory/items")).json()

    async def quote():
        if failure == "unavailable":
            raise HTTPException(503, "Market unavailable")
        return {"gram_24k_usd": "100", "fetched_at": datetime.now(UTC).isoformat(), "stale": True}

    monkeypatch.setattr(purchase_service, "get_quote", quote)
    monkeypatch.setattr(sale_service, "get_quote", quote)
    requests = {
        "bulk_purchase": (
            "/api/v1/purchases/customer-stock",
            {
                "location_id": s["location"],
                "product_id": s["bulk"],
                "weight": "2",
                "paid_usd": "100",
            },
        ),
        "item_sale": (
            "/api/v1/sales/item",
            {
                "location_id": s["location"],
                "items": [
                    {"inventory_item_id": items[0]["id"], "discount": "0", "sell_price": "100"}
                ],
            },
        ),
        "bulk_sale": (
            "/api/v1/sales/stock",
            {
                "location_id": s["location"],
                "item": {
                    "supplier_id": s["supplier"],
                    "gold_purity_id": s["p18"],
                    "weight": "2",
                    "gold_charge_in_grams": "2",
                    "making_charge": "1",
                },
            },
        ),
    }
    url, body = requests[flow]
    result = await client.post(url, json=body, headers={"Idempotency-Key": "failed-trade"})
    assert result.status_code == 503, result.text
    async with test_session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(Purchase)) == 1
        assert await db.scalar(select(func.count()).select_from(PurchaseStock)) == 0
        assert await db.scalar(select(func.count()).select_from(Sale)) == 1  # setup cash receipt
        assert (
            await db.scalar(
                select(func.count())
                .select_from(InventoryItem)
                .where(InventoryItem.status == "sold")
            )
            == 0
        )
        assert (
            await db.scalar(
                select(InventoryBalance.total_weight).where(InventoryBalance.purity_id == s["p18"])
            )
            == 100
        )
        assert await db.scalar(select(func.sum(CashEntry.amount_usd))) == 1000
