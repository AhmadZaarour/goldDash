"""Customer ounce adjustments affect recorded rates, never manually entered payments."""

import asyncio
from decimal import ROUND_HALF_UP, Decimal
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select

from app.models import Product, Purchase
from app.services import gold_price
from tests.api.test_backend_access import headers_for
from tests.api.test_gold_workflows import invoice, setup_shop

pytestmark = pytest.mark.asyncio(loop_scope="session")
URL = "/api/v1/gold-price/settings"
MARKET = Decimal("100.5") * Decimal("31.1")


async def save(client, buy="0", sell="0", unit="showroom"):
    response = await client.put(
        URL,
        json={"buy_adjustment_usd": buy, "sell_adjustment_usd": sell},
        headers={"X-Business-Unit": unit},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def purchase_bulk(client, s, *, amount="250", key=None, unit="showroom"):
    return await client.post(
        "/api/v1/purchases/customer-stock",
        json={
            "location_id": s["location"],
            "product_id": s["bulk"],
            "weight": "5",
            "paid_usd": amount,
            "placement": unit,
        },
        headers={"Idempotency-Key": key or uuid4().hex, "X-Business-Unit": unit},
    )


async def test_defaults_zero_and_settings_are_workspace_owned_admin_only(
    client, test_session_factory
):
    defaults = (await client.get(URL)).json()
    assert Decimal(defaults["buy_adjustment_usd"]) == 0
    assert Decimal(defaults["sell_adjustment_usd"]) == 0
    changed = await save(client, "-40", "40")
    assert changed["updated_by"] is not None and changed["updated_at"] is not None
    factory = (await client.get(URL, headers={"X-Business-Unit": "factory"})).json()
    assert Decimal(factory["buy_adjustment_usd"]) == 0
    await save(client, "-20", "25", "factory")
    assert Decimal((await client.get(URL)).json()["buy_adjustment_usd"]) == -40
    for role in ["cashier", "employee"]:
        headers = await headers_for(test_session_factory, role)
        assert (await client.get(URL, headers=headers)).status_code == 200
        assert (
            await client.put(
                URL,
                json={"buy_adjustment_usd": "-99", "sell_adjustment_usd": "99"},
                headers=headers,
            )
        ).status_code == 403
    assert (await client.get(URL, headers={"Authorization": ""})).status_code == 401
    assert (
        await client.put(
            URL,
            json={"buy_adjustment_usd": "0", "sell_adjustment_usd": "0"},
            headers={"X-Business-Unit": "legacy"},
        )
    ).status_code == 403


@pytest.mark.parametrize("invalid", [None, "NaN", "Infinity", "0.001", "10000000000.00"])
async def test_settings_reject_invalid_offsets(client, invalid):
    response = await client.put(
        URL, json={"buy_adjustment_usd": invalid, "sell_adjustment_usd": "0"}
    )
    assert response.status_code == 422
    assert Decimal((await client.get(URL)).json()["buy_adjustment_usd"]) == 0


@pytest.mark.parametrize("karat,percentage", [(18, "75"), (21, "87.5"), (24, "99.5")])
async def test_buying_adjustment_precedes_gram_conversion_and_actual_payment_is_manual(
    client, test_session_factory, karat, percentage
):
    s = await setup_shop(client, test_session_factory)
    async with test_session_factory() as db:
        bulk = await db.get(Product, s["bulk"])
        bulk.purity_id = s[f"p{karat}"]
        await db.commit()
    await save(client, "-40", "40")
    response = await purchase_bulk(client, s, key="buy")
    assert response.status_code == 201, response.text
    record = response.json()
    assert Decimal(record["market_ounce_usd"]) == MARKET
    assert Decimal(record["ounce_adjustment_usd"]) == -40
    assert Decimal(record["applied_ounce_usd"]) == MARKET - 40
    assert Decimal(record["paid_usd"]) == 250
    line = (await client.get(f"/api/v1/purchases/stock/{record['id']}")).json()
    expected = ((MARKET - 40) / Decimal("31.1") * Decimal(percentage) / Decimal("99.5")).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )
    assert Decimal(line["gold_price_per_gram"]) == expected
    assert Decimal(line["cost_per_gram"]) == 50
    await save(client, "-80", "80")
    replay = await purchase_bulk(client, s, key="buy")
    assert replay.json() == record
    saved = (await client.get(f"/api/v1/purchases/{record['id']}")).json()
    assert Decimal(saved.pop("paid_usd")) == Decimal(record["paid_usd"])
    assert saved == {key: value for key, value in record.items() if key != "paid_usd"}
    summary = (
        await client.get("/api/v1/cash/summary", params={"location_id": s["location"]})
    ).json()
    assert Decimal(summary["net_usd"]) == 750


@pytest.mark.parametrize("karat,percentage", [(18, "75"), (21, "87.5"), (24, "99.5")])
async def test_selling_adjustment_is_snapshotted_and_customer_total_remains_manual(
    client, test_session_factory, karat, percentage
):
    s = await setup_shop(client, test_session_factory)
    async with test_session_factory() as db:
        product = await db.get(Product, s["item18"])
        product.purity_id = s[f"p{karat}"]
        await db.commit()
    await save(client, "-40", "40")
    purchased = await client.post("/api/v1/purchases/item", json=invoice(s))
    assert purchased.status_code == 201, purchased.text
    assert purchased.json()["ounce_adjustment_usd"] is None
    items = (await client.get("/api/v1/inventory/items")).json()
    item = next(row for row in items if row["product_id"] == s["item18"])
    sold = await client.post(
        "/api/v1/sales/item",
        json={
            "location_id": s["location"],
            "items": [{"inventory_item_id": item["id"], "discount": "0", "sell_price": "777.77"}],
        },
    )
    assert sold.status_code == 201, sold.text
    record = sold.json()
    assert Decimal(record["market_ounce_usd"]) == MARKET
    assert Decimal(record["ounce_adjustment_usd"]) == 40
    assert Decimal(record["applied_ounce_usd"]) == MARKET + 40
    lines = (await client.get(f"/api/v1/sales/item/{record['id']}")).json()
    expected = ((MARKET + 40) / Decimal("31.1") * Decimal(percentage) / Decimal("99.5")).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )
    assert Decimal(lines[0]["gold_price_per_gram"]) == expected
    assert Decimal(lines[0]["sell_price"]) == Decimal("777.77")
    await save(client, "-99", "99")
    assert (await client.get(f"/api/v1/sales/{record['id']}")).json() == record
    assert (await client.get(f"/api/v1/sales/item/{record['id']}")).json() == lines


async def test_nonpositive_adjusted_price_blocks_trade_without_posting_resources(
    client, test_session_factory
):
    s = await setup_shop(client, test_session_factory)
    await save(client, "-4000", "0")
    response = await purchase_bulk(client, s)
    assert response.status_code == 422, response.text
    async with test_session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(Purchase)) == 0
    assert (
        Decimal(
            (
                await client.get("/api/v1/cash/summary", params={"location_id": s["location"]})
            ).json()["net_usd"]
        )
        == 1000
    )


async def test_customer_profiles_share_the_raw_cache_across_workspaces(
    client, test_redis, monkeypatch
):
    monkeypatch.setattr(gold_price, "redis", test_redis)
    calls = []

    async def upstream(request):
        calls.append(request)
        return httpx.Response(200, json={"price": 3110})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        gold_price.httpx,
        "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(upstream), **kw),
    )
    await save(client, "-40", "40")
    await save(client, "-20", "20", "factory")
    showroom = (await client.get("/api/v1/gold-price")).json()
    assert Decimal(showroom["ounce_usd"]) == 3110
    assert Decimal(showroom["customer_buy"]["ounce_usd"]) == 3070
    assert Decimal(showroom["customer_sell"]["ounce_usd"]) == 3150
    await asyncio.gather(
        *[
            client.get("/api/v1/gold-price", headers={"X-Business-Unit": "factory"})
            for _ in range(4)
        ]
    )
    factory = (
        await client.get("/api/v1/gold-price", headers={"X-Business-Unit": "factory"})
    ).json()
    assert Decimal(factory["customer_buy"]["ounce_usd"]) == 3090
    assert len(calls) == 1
    await save(client, "-4000", "0")
    invalid = (await client.get("/api/v1/gold-price")).json()
    assert invalid["customer_buy"]["available"] is False
    assert invalid["customer_sell"]["available"] is True
    assert Decimal(invalid["ounce_usd"]) == 3110
    assert len(calls) == 1


async def test_factory_bulk_entries_use_the_factory_buying_adjustment(client, test_session_factory):
    s = await setup_shop(client, test_session_factory)
    await save(client, "-40", "40", "showroom")
    await save(client, "-20", "20", "factory")
    response = await purchase_bulk(client, s, amount="0", unit="factory")
    assert response.status_code == 201, response.text
    assert response.json()["source"] == "opening"
    assert Decimal(response.json()["ounce_adjustment_usd"]) == -20
    assert Decimal(response.json()["paid_usd"]) == 0
    assert (await client.get(f"/api/v1/purchases/{response.json()['id']}")).status_code == 404


async def test_manual_quote_drives_trade_and_preserves_customer_adjustments(
    client, test_session_factory
):
    shop = await setup_shop(client, test_session_factory)
    await save(client, "-40", "20")
    mode = await client.put("/api/v1/gold-price/quote-mode", json={"manual_ounce_usd": "4000"})
    assert mode.status_code == 200, mode.text
    assert Decimal(mode.json()["buy_adjustment_usd"]) == -40
    assert Decimal(mode.json()["sell_adjustment_usd"]) == 20
    changed = await save(client, "-50", "20")
    assert Decimal(changed["manual_ounce_usd"]) == 4000
    trade = await purchase_bulk(client, shop)
    assert trade.status_code == 201, trade.text
    assert Decimal(trade.json()["market_ounce_usd"]) == 4000
    assert Decimal(trade.json()["applied_ounce_usd"]) == 3950
