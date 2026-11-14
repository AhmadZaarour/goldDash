"""Independent ownership at one address, production, and paired internal trade."""

import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models import Category, GoldPurity, Location, Product, Supplier
from app.services import operations_service
from tests.api.test_backend_access import headers_for

pytestmark = pytest.mark.asyncio(loop_scope="session")


def header(unit, key=None):
    return {"X-Business-Unit": unit, **({"Idempotency-Key": key or uuid4().hex})}


async def shop(factory):
    async with factory() as db:
        purity = GoldPurity(name="18K", karat=18, purity=75)
        reference = GoldPurity(name="24K", karat=24, purity=Decimal("99.5"))
        location = Location(name="One business", code="ONE")
        category = Category(name="Pieces")
        supplier = Supplier(name="Shared supplier", phone="123")
        db.add_all([purity, reference, location, category, supplier])
        await db.flush()
        item = Product(
            name="Ring",
            sku="RING",
            category_id=category.id,
            purity_id=purity.id,
            inventory_type="item",
        )
        bulk = Product(
            name="Bulk",
            sku="BULK",
            category_id=category.id,
            purity_id=purity.id,
            inventory_type="bulk",
        )
        db.add_all([item, bulk])
        await db.commit()
        return {
            "purity": purity.id,
            "location": location.id,
            "item": item.id,
            "bulk": bulk.id,
            "supplier": supplier.id,
        }


async def seed(client, s, unit, cash="1000", gold="0", value="0", key=None):
    return await client.post(
        "/api/v1/operations/opening",
        json={
            "location_id": s["location"],
            "cash_usd": cash,
            "gold": []
            if gold == "0"
            else [{"purity_id": s["purity"], "weight": gold, "value_usd": value}],
            "note": "Opening balances",
        },
        headers=header(unit, key),
    )


async def overview(client, s, unit):
    response = await client.get(
        "/api/v1/operations/overview", params={"location_id": s["location"]}, headers=header(unit)
    )
    assert response.status_code == 200, response.text
    return response.json()


async def produce(client, s):
    return await client.post(
        "/api/v1/operations/production",
        json={
            "location_id": s["location"],
            "inputs": [{"purity_id": s["purity"], "weight": "100"}],
            "pieces": [
                {"product_id": s["item"], "weight": "5"},
                {"product_id": s["item"], "weight": "5"},
            ],
            "scrap": [{"purity_id": s["purity"], "weight": "90"}],
            "direct_cost_usd": "20",
        },
        headers=header("factory"),
    )


async def test_opening_cash_gold_and_actual_cost_are_independent_at_same_location(
    client, test_session_factory
):
    s = await shop(test_session_factory)
    results = await asyncio.gather(
        seed(client, s, "factory", "1000", "100", "5000", "opening"),
        seed(client, s, "factory", "1000", "100", "5000", "opening"),
    )
    assert [r.status_code for r in results] == [201, 201], [r.text for r in results]
    assert results[0].json() == results[1].json()
    assert (await seed(client, s, "showroom", "200", "10", "600", "opening")).status_code == 201
    f = await overview(client, s, "factory")
    r = await overview(client, s, "showroom")
    assert Decimal(f["cash_usd"]) == 1000
    assert Decimal(r["cash_usd"]) == 200
    assert Decimal(f["bulk"][0]["total_weight"]) == 100
    assert Decimal(r["bulk"][0]["total_weight"]) == 10
    assert Decimal(f["bulk"][0]["cost_usd"]) == 5000
    assert (await seed(client, s, "factory")).status_code == 409
    # Showroom cannot fund a purchase with the factory drawer.
    response = await client.post(
        "/api/v1/purchases/customer-stock",
        json={
            "location_id": s["location"],
            "product_id": s["bulk"],
            "weight": "1",
            "paid_usd": "300",
        },
        headers=header("showroom"),
    )
    assert response.status_code == 409, response.text


async def test_cash_and_gold_transfers_are_paired_not_profit(client, test_session_factory):
    s = await shop(test_session_factory)
    assert (await seed(client, s, "factory", "1000", "100", "5000")).status_code == 201
    assert (await seed(client, s, "showroom", "100")).status_code == 201
    cash = await client.post(
        "/api/v1/operations/cash-transfers",
        json={
            "location_id": s["location"],
            "to_unit": "showroom",
            "to_location_id": s["location"],
            "amount_usd": "250",
            "note": "Working capital",
        },
        headers=header("factory"),
    )
    assert cash.status_code == 201, cash.text
    gold = await client.post(
        "/api/v1/operations/gold-transfers",
        json={
            "location_id": s["location"],
            "to_unit": "showroom",
            "to_location_id": s["location"],
            "purity_id": s["purity"],
            "weight": "10",
            "note": "Repayment reserve",
        },
        headers=header("factory"),
    )
    assert gold.status_code == 201, gold.text
    f = await overview(client, s, "factory")
    r = await overview(client, s, "showroom")
    assert Decimal(f["cash_usd"]) == 750
    assert Decimal(r["cash_usd"]) == 350
    assert Decimal(f["bulk"][0]["cost_usd"]) == 4500
    assert Decimal(r["bulk"][0]["cost_usd"]) == 500
    rev = await client.post(
        f"/api/v1/operations/history/{cash.json()['id']}/reverse",
        json={"note": "Correction"},
        headers=header("showroom"),
    )
    assert rev.status_code == 201, rev.text
    assert Decimal((await overview(client, s, "factory"))["cash_usd"]) == 1000


async def test_production_internal_sale_customer_sale_and_payment(
    client, test_session_factory, monkeypatch, purchase_market_quote
):
    async def quote():
        from datetime import UTC, datetime

        return {
            "gram_24k_usd": "100.5",
            "fetched_at": datetime.now(UTC).isoformat(),
            "stale": False,
        }

    monkeypatch.setattr(operations_service, "get_quote", quote)
    s = await shop(test_session_factory)
    await seed(client, s, "factory", "1000", "100", "5000")
    await seed(client, s, "showroom", "100")
    batch = await produce(client, s)
    assert batch.status_code == 201, batch.text
    assert Decimal(batch.json()["total_cost_usd"]) == 520
    item_id = batch.json()["inventory_item_ids"][0]
    assert (
        await client.get(f"/api/v1/inventory/items/{item_id}", headers=header("showroom"))
    ).status_code == 404
    f = await overview(client, s, "factory")
    assert Decimal(f["cash_usd"]) == 980
    assert Decimal(f["bulk"][0]["total_weight"]) == 90
    assert Decimal(f["bulk"][0]["cost_usd"]) == 4500
    supplied = await client.post(
        "/api/v1/operations/internal-invoices",
        json={
            "location_id": s["location"],
            "showroom_location_id": s["location"],
            "gold_price_usd": "100",
            "pieces": [{"inventory_item_id": item_id, "making_usd": "10"}],
        },
        headers=header("factory"),
    )
    assert supplied.status_code == 201, supplied.text
    assert Decimal(supplied.json()["total_value_usd"]) == Decimal("386.9")
    showroom_item = await client.get(
        f"/api/v1/inventory/items/{item_id}", headers=header("showroom")
    )
    assert showroom_item.status_code == 200, showroom_item.text
    assert Decimal(showroom_item.json()["base_cost_usd"]) == Decimal("386.90")
    assert (
        await client.get(f"/api/v1/inventory/items/{item_id}", headers=header("factory"))
    ).status_code == 404
    sale = await client.post(
        "/api/v1/sales/item",
        json={
            "location_id": s["location"],
            "items": [{"inventory_item_id": item_id, "discount": "0", "sell_price": "500"}],
        },
        headers=header("showroom"),
    )
    assert sale.status_code == 201, sale.text
    payment = await client.post(
        "/api/v1/operations/internal-payments",
        json={
            "showroom_location_id": s["location"],
            "factory_location_id": s["location"],
            "cash_gold_usd": "376.9",
            "gold_price_usd": "100",
            "making_usd": "10",
            "close_account": True,
            "note": "Pay factory",
        },
        headers=header("showroom"),
    )
    assert payment.status_code == 201, payment.text
    balance = (
        await client.get("/api/v1/operations/internal-balance", headers=header("factory"))
    ).json()
    assert balance["is_settled"]
    assert Decimal((await overview(client, s, "factory"))["cash_usd"]) == Decimal("1366.9")
    assert Decimal((await overview(client, s, "showroom"))["cash_usd"]) == Decimal("213.1")


async def test_workspace_permissions_and_wrong_trade_directions(client, test_session_factory):
    s = await shop(test_session_factory)
    headers = await headers_for(test_session_factory, "cashier", workspace_access="showroom")
    assert (
        await client.get(
            "/api/v1/cash/summary",
            params={"location_id": s["location"]},
            headers={**headers, **header("factory")},
        )
    ).status_code == 403
    assert (
        await client.get("/api/v1/operations/legacy", headers={**headers, **header("legacy")})
    ).status_code == 403
    assert (
        await client.post("/api/v1/purchases/item", json={}, headers=header("factory"))
    ).status_code in (403, 422)
    assert (
        await client.post("/api/v1/sales/stock", json={}, headers=header("showroom"))
    ).status_code in (403, 422)
    assert (
        await client.post(
            "/api/v1/operations/opening", json={}, headers={**headers, **header("showroom")}
        )
    ).status_code == 403


async def report(client, unit, company=False):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    month = datetime.now(ZoneInfo("Asia/Beirut")).strftime("%Y-%m")
    response = await client.get(
        "/api/v1/operations/profit",
        params={"month": month, "company": company},
        headers=header(unit),
    )
    assert response.status_code == 200, response.text
    return response.json()


async def supply(client, s, item_id):
    response = await client.post(
        "/api/v1/operations/internal-invoices",
        json={
            "location_id": s["location"],
            "showroom_location_id": s["location"],
            "gold_price_usd": "100",
            "pieces": [{"inventory_item_id": item_id, "making_usd": "10"}],
        },
        headers=header("factory"),
    )
    assert response.status_code == 201, response.text
    return response


async def reverse(client, unit, path):
    return await client.post(
        "/api/v1/operations/" + path + "/reverse",
        json={"note": "Audited correction"},
        headers=header(unit),
    )


async def test_profit_eliminates_internal_markup_and_restores_cost_on_return(
    client, test_session_factory
):
    s = await shop(test_session_factory)
    await seed(client, s, "factory", "1000", "100", "5000")
    await seed(client, s, "showroom", "100")
    batch = await produce(client, s)
    item = batch.json()["inventory_item_ids"][0]
    await supply(client, s, item)
    assert Decimal((await report(client, "factory"))["profit_usd"]) == Decimal("126.90")
    assert Decimal((await report(client, "showroom"))["profit_usd"]) == 0
    assert Decimal((await report(client, "factory", True))["profit_usd"]) == 0
    sale = await client.post(
        "/api/v1/sales/item",
        json={
            "location_id": s["location"],
            "items": [{"inventory_item_id": item, "discount": "0", "sell_price": "500"}],
        },
        headers=header("showroom"),
    )
    assert sale.status_code == 201, sale.text
    assert Decimal((await report(client, "showroom"))["profit_usd"]) == Decimal("113.10")
    assert Decimal((await report(client, "factory", True))["profit_usd"]) == 240
    lines = (
        await client.get(f"/api/v1/sales/item/{sale.json()['id']}", headers=header("showroom"))
    ).json()
    returned = await client.post(
        "/api/v1/inventory/returns",
        json={"sale_item_id": lines[0]["id"], "location_id": s["location"], "refund_usd": "500"},
        headers=header("showroom"),
    )
    assert returned.status_code == 201, returned.text
    assert Decimal((await report(client, "factory", True))["profit_usd"]) == 0
    assert Decimal((await report(client, "showroom"))["profit_usd"]) == 0


async def test_production_invoice_reversal_restores_ownership_gold_and_cash(
    client, test_session_factory
):
    s = await shop(test_session_factory)
    await seed(client, s, "factory", "1000", "100", "5000")
    await seed(client, s, "showroom", "100")
    batch = await produce(client, s)
    invoice = await supply(client, s, batch.json()["inventory_item_ids"][0])
    blocked = await reverse(client, "factory", f"production/{batch.json()['id']}")
    assert blocked.status_code == 409, blocked.text
    assert (
        await reverse(client, "showroom", f"internal-invoices/{invoice.json()['id']}")
    ).status_code == 201
    assert (
        await reverse(client, "factory", f"internal-invoices/{invoice.json()['id']}")
    ).status_code == 409
    assert Decimal((await report(client, "factory"))["profit_usd"]) == 0
    assert (await reverse(client, "factory", f"production/{batch.json()['id']}")).status_code == 201
    assert (await reverse(client, "factory", f"production/{batch.json()['id']}")).status_code == 409
    stock = await overview(client, s, "factory")
    assert Decimal(stock["cash_usd"]) == 1000
    assert Decimal(stock["bulk"][0]["total_weight"]) == 100
    assert Decimal(stock["bulk"][0]["cost_usd"]) == 5000
    assert stock["available_pieces"] == 0


async def test_gold_payment_uses_repayment_factor_and_saved_cost_on_reversal(
    client, test_session_factory
):
    s = await shop(test_session_factory)
    await seed(client, s, "factory", "1000", "100", "5000")
    await seed(client, s, "showroom", "100", "10", "600")
    batch = await produce(client, s)
    await supply(client, s, batch.json()["inventory_item_ids"][0])
    payment = await client.post(
        "/api/v1/operations/internal-payments",
        json={
            "showroom_location_id": s["location"],
            "factory_location_id": s["location"],
            "purity_id": s["purity"],
            "gold_grams": "5",
            "making_usd": "10",
            "note": "18K repayment",
        },
        headers=header("showroom"),
    )
    assert payment.status_code == 201, payment.text
    balance = (
        await client.get("/api/v1/operations/internal-balance", headers=header("showroom"))
    ).json()
    assert Decimal(balance["gold_24k"]) == Decimal("0.069")
    async with test_session_factory() as db:
        purity = await db.get(GoldPurity, s["purity"])
        purity.repayment_factor = Decimal("0.5")
        await db.commit()
    assert (
        await reverse(client, "factory", f"internal-payments/{payment.json()['id']}")
    ).status_code == 201
    assert (
        await reverse(client, "factory", f"internal-payments/{payment.json()['id']}")
    ).status_code == 409
    restored = await overview(client, s, "showroom")
    assert Decimal(restored["bulk"][0]["total_weight"]) == 10
    assert Decimal(restored["bulk"][0]["cost_usd"]) == 600
    assert Decimal(restored["cash_usd"]) == 100


async def test_capital_adjustments_dates_valuations_and_conservation(client, test_session_factory):
    s = await shop(test_session_factory)
    await seed(client, s, "factory", "1000", "100", "5000")
    capital = await client.post(
        "/api/v1/operations/capital",
        json={
            "location_id": s["location"],
            "cash_usd": "100",
            "gold": [{"purity_id": s["purity"], "weight": "10", "value_usd": "700"}],
            "effective_at": "2026-01-01T10:00:00Z",
            "note": "Additional capital",
        },
        headers=header("factory"),
    )
    assert capital.status_code == 201, capital.text
    adjustment = await client.post(
        "/api/v1/operations/adjustments",
        json={
            "location_id": s["location"],
            "cash_usd": "-50",
            "gold": [{"purity_id": s["purity"], "weight": "-10"}],
            "note": "Count correction",
        },
        headers=header("factory"),
    )
    assert adjustment.status_code == 201, adjustment.text
    assert (
        await reverse(client, "factory", f"history/{adjustment.json()['id']}")
    ).status_code == 201
    assert (await reverse(client, "factory", f"history/{capital.json()['id']}")).status_code == 201
    stock = await overview(client, s, "factory")
    assert Decimal(stock["cash_usd"]) == 1000
    assert Decimal(stock["bulk"][0]["cost_usd"]) == 5000
    value = await client.post(
        "/api/v1/operations/stock-value",
        json={
            "location_id": s["location"],
            "purity_id": s["purity"],
            "value_usd": "5100",
            "note": "Opening value correction",
        },
        headers=header("factory"),
    )
    assert value.status_code == 201, value.text
    assert Decimal((await overview(client, s, "factory"))["bulk"][0]["cost_usd"]) == 5100
    assert Decimal((await report(client, "factory"))["profit_usd"]) == 0
    invalid = await client.post(
        "/api/v1/operations/production",
        json={
            "location_id": s["location"],
            "inputs": [{"purity_id": s["purity"], "weight": "100"}],
            "pieces": [{"product_id": s["item"], "weight": "101"}],
        },
        headers=header("factory"),
    )
    assert invalid.status_code == 409, invalid.text
    assert Decimal((await overview(client, s, "factory"))["bulk"][0]["total_weight"]) == 100


async def test_factory_supplier_sale_is_receivable_and_received_gold_has_production_value(
    client, test_session_factory
):
    s = await shop(test_session_factory)
    await seed(client, s, "factory", "1000", "100", "5000")
    batch = await produce(client, s)
    item = batch.json()["inventory_item_ids"][0]
    sale = await client.post(
        "/api/v1/operations/supplier-item-sales",
        json={
            "location_id": s["location"],
            "supplier_id": s["supplier"],
            "pieces": [{"inventory_item_id": item, "making_usd": "10"}],
        },
        headers=header("factory"),
    )
    assert sale.status_code == 201, sale.text
    assert Decimal((await overview(client, s, "factory"))["cash_usd"]) == 980
    ledger = (
        await client.get(f"/api/v1/suppliers/{s['supplier']}/balance", headers=header("factory"))
    ).json()
    assert Decimal(ledger["gold_24k"]) == Decimal("-3.769")
    assert Decimal(ledger["making_usd"]) == -10
    settled = await client.post(
        f"/api/v1/suppliers/{s['supplier']}/settlements",
        json={
            "idempotency_key": "receivegold",
            "direction": "received",
            "location_id": s["location"],
            "purity_id": s["purity"],
            "gold_grams": "5",
            "making_usd": "10",
        },
        headers=header("factory"),
    )
    assert settled.status_code == 201, settled.text
    history = (
        await client.get(f"/api/v1/suppliers/{s['supplier']}/ledger", headers=header("factory"))
    ).json()
    receipt = history[-1]
    assert Decimal(receipt["stock_value_usd"]) > 0
    assert Decimal((await overview(client, s, "factory"))["bulk"][0]["cost_usd"]) > 4500
    reversal = await client.post(
        f"/api/v1/suppliers/{s['supplier']}/ledger/{receipt['id']}/reverse",
        json={"idempotency_key": "undo", "reason": "Correction"},
        headers=header("factory"),
    )
    assert reversal.status_code == 201, reversal.text
    assert Decimal((await overview(client, s, "factory"))["bulk"][0]["cost_usd"]) == 4500


async def test_legacy_assignment_keeps_history_separate_and_is_audited(
    client, test_session_factory
):
    from sqlalchemy import update

    from app.models import InventoryBalance

    s = await shop(test_session_factory)
    async with test_session_factory() as db:
        row = InventoryBalance(
            unit="showroom",
            location_id=s["location"],
            purity_id=s["purity"],
            placement="factory",
            total_weight=100,
            cost_usd=None,
        )
        db.add(row)
        await db.flush()
        row_id = row.id
        await db.execute(
            update(InventoryBalance).where(InventoryBalance.id == row_id).values(unit=None)
        )
        await db.commit()
    assert (await overview(client, s, "showroom"))["bulk"] == []
    assert (await overview(client, s, "factory"))["bulk"] == []
    legacy = await client.get("/api/v1/operations/legacy?kind=stock", headers=header("legacy"))
    assert legacy.status_code == 200, legacy.text
    assert legacy.json()[0]["id"] == row_id
    # Explicitly assign this historical factory bucket to Showroom, ignoring placement.
    assigned = await client.post(
        "/api/v1/operations/legacy/assign",
        json={
            "kind": "stock",
            "id": row_id,
            "unit": "showroom",
            "note": "Owner reviewed historical stock",
        },
        headers=header("legacy"),
    )
    assert assigned.status_code == 201, assigned.text
    assert (await overview(client, s, "showroom"))["bulk"][0]["unit"] == "showroom"
    assert (await overview(client, s, "factory"))["bulk"] == []
    assert (
        await client.post(
            "/api/v1/operations/capital",
            json={"location_id": s["location"], "cash_usd": "1", "note": "Invalid legacy write"},
            headers=header("legacy"),
        )
    ).status_code == 403


async def test_staff_membership_edit_takes_effect_without_token_renewal(
    client, test_session_factory
):
    from app.models import User

    staff_headers = await headers_for(test_session_factory, "cashier", workspace_access="showroom")
    async with test_session_factory() as db:
        staff = await db.scalar(select(User).where(User.role == "cashier"))
        staff_id = staff.id
    response = await client.patch(
        f"/api/v1/operations/staff/{staff_id}",
        json={"workspace_access": "factory"},
        headers=header("showroom"),
    )
    assert response.status_code == 200, response.text
    assert (
        await client.get(
            "/api/v1/operations/overview", headers={**staff_headers, **header("showroom")}
        )
    ).status_code == 403
    assert (
        await client.get(
            "/api/v1/operations/overview", headers={**staff_headers, **header("factory")}
        )
    ).status_code == 200
    users = (await client.get("/api/v1/operations/staff", headers=header("showroom"))).json()
    assert all("password" not in str(row) for row in users)
