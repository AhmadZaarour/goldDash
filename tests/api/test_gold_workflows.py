"""Accounting behavior across mixed karats, physical resources, cash and retries."""

import asyncio
import io
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from PIL import Image
from sqlalchemy import func, select

from app.models import (
    Category,
    GoldPurity,
    InventoryBalance,
    InventoryItem,
    Location,
    Product,
    Purchase,
    Sale,
    Supplier,
    SupplierLedgerEntry,
    User,
)
from app.models.cashLedger import CashEntry
from app.services.gold_conversion import allocate_charge
from tests.api.test_backend_access import headers_for

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def setup_shop(client, factory):
    async with factory() as db:
        actor = await db.scalar(select(User))
        p18 = GoldPurity(name="18K", karat=18, purity=Decimal(75))
        p21 = GoldPurity(name="21K", karat=21, purity=Decimal("87.5"))
        p24 = GoldPurity(name="24K", karat=24, purity=Decimal("99.5"))
        loc = Location(name="Shop", code="SHOP", is_active=True)
        supplier = Supplier(name="Supplier", phone="123", is_active=True)
        cat = Category(name="Gold")
        db.add_all([p18, p21, p24, loc, supplier, cat])
        await db.flush()
        item18 = Product(
            name="Ring18", sku="R18", category_id=cat.id, purity_id=p18.id, inventory_type="item"
        )
        item21 = Product(
            name="Ring21", sku="R21", category_id=cat.id, purity_id=p21.id, inventory_type="item"
        )
        bulk = Product(
            name="Bulk18", sku="B18", category_id=cat.id, purity_id=p18.id, inventory_type="bulk"
        )
        db.add_all([item18, item21, bulk])
        await db.flush()
        sale = Sale(location_id=loc.id, created_by=actor.id)
        db.add(sale)
        await db.flush()
        db.add(
            CashEntry(
                location_id=loc.id,
                sale_id=sale.id,
                kind="sale",
                amount_usd=1000,
                created_by=actor.id,
            )
        )
        db.add_all(
            [
                InventoryBalance(
                    purity_id=p18.id, location_id=loc.id, placement="factory", total_weight=100
                ),
                InventoryBalance(
                    purity_id=p21.id, location_id=loc.id, placement="factory", total_weight=100
                ),
            ]
        )
        await db.commit()
        return dict(
            supplier=supplier.id,
            location=loc.id,
            p18=p18.id,
            p21=p21.id,
            p24=p24.id,
            item18=item18.id,
            item21=item21.id,
            bulk=bulk.id,
        )


def invoice(s):
    return {
        "supplier_id": s["supplier"],
        "location_id": s["location"],
        "total_gold_charge_grams": "20",
        "items": [
            {
                "supplier_id": s["supplier"],
                "product_id": s[key],
                "weight": "10",
                "gold_price_per_gram": "100",
                "making_charge": "5",
            }
            for key in ["item18", "item21"]
        ],
    }


async def test_mixed_invoice_allocates_cost_and_snapshots_debt(client, test_session_factory):
    s = await setup_shop(client, test_session_factory)
    body = invoice(s)
    response = await client.post("/api/v1/purchases/item", json=body)
    assert response.status_code == 201, response.text
    assert Decimal(response.json()["gold_debt_24k"]) == Decimal("16.332")
    lines = (await client.get(f"/api/v1/purchases/items/{response.json()['id']}")).json()
    assert [Decimal(line["gold_charge_in_grams"]) for line in lines] == [
        Decimal("9.231"),
        Decimal("10.769"),
    ]
    balance = (await client.get(f"/api/v1/suppliers/{s['supplier']}/balance")).json()
    assert Decimal(balance["gold_24k"]) == Decimal("16.332")
    assert Decimal(balance["making_usd"]) == 10
    await client.patch(f"/api/v1/goldpurities/{s['p18']}", json={"purity": "74"})
    assert (await client.get(f"/api/v1/suppliers/{s['supplier']}/balance")).json() == balance
    body["total_gold_charge_grams"] = "21"
    assert (await client.post("/api/v1/purchases/item", json=body)).status_code == 409
    assert allocate_charge(Decimal("0.003"), [Decimal("0.9"), Decimal("0.9"), Decimal("0.1")]) == [
        Decimal("0.002"),
        Decimal("0.001"),
        Decimal("0"),
    ]


@pytest.mark.parametrize("purity_key,factor", [("p18", "0.74"), ("p21", "0.865")])
async def test_converted_payment_cash_and_exact_reversal(
    client, test_session_factory, purity_key, factor
):
    s = await setup_shop(client, test_session_factory)
    assert (await client.post("/api/v1/purchases/item", json=invoice(s))).status_code == 201
    url = f"/api/v1/suppliers/{s['supplier']}"
    before = (await client.get(url + "/balance")).json()
    payload = {
        "idempotency_key": "pay",
        "direction": "sent",
        "location_id": s["location"],
        "purity_id": s[purity_key],
        "gold_grams": "2",
        "cash_gold_usd": "100",
        "gold_price_usd": "80",
        "making_usd": "3",
    }
    paid = await client.post(url + "/settlements", json=payload)
    assert paid.status_code == 201, paid.text
    expected = Decimal(before["gold_24k"]) - 2 * Decimal(factor) - Decimal("1.25")
    assert Decimal(paid.json()["gold_24k"]) == expected
    assert Decimal(paid.json()["making_usd"]) == 7
    async with test_session_factory() as db:
        entry = await db.scalar(
            select(SupplierLedgerEntry).where(SupplierLedgerEntry.kind == "settlement")
        )
        entry_id = entry.id
        assert entry.physical_gold_grams == Decimal(-2)
        assert entry.valuation_factor == Decimal(factor)
        assert (
            await db.scalar(
                select(InventoryBalance.total_weight).where(
                    InventoryBalance.purity_id == s[purity_key]
                )
            )
            == 98
        )
        assert await db.scalar(select(func.sum(CashEntry.amount_usd))) == 897
    await client.patch(f"/api/v1/goldpurities/{s[purity_key]}", json={"repayment_factor": "0.9"})
    assert (await client.post(url + "/settlements", json=payload)).status_code == 409
    reversed_ = await client.post(
        url + f"/ledger/{entry_id}/reverse",
        json={"idempotency_key": "undo", "reason": "Correction"},
    )
    assert reversed_.status_code == 201, reversed_.text
    assert (await client.get(url + "/balance")).json() == before
    async with test_session_factory() as db:
        assert (
            await db.scalar(
                select(InventoryBalance.total_weight).where(
                    InventoryBalance.purity_id == s[purity_key]
                )
            )
            == 100
        )
        assert await db.scalar(select(func.sum(CashEntry.amount_usd))) == 1000


async def test_cashier_customer_bulk_is_atomic_retryable_and_has_no_debt(
    client, test_session_factory
):
    s = await setup_shop(client, test_session_factory)
    cashier = await headers_for(test_session_factory, "cashier")
    headers = {**cashier, "Idempotency-Key": "walk-in"}
    body = {
        "location_id": s["location"],
        "product_id": s["bulk"],
        "weight": "5",
        "paid_usd": "250",
        "placement": "factory",
    }
    results = await asyncio.gather(
        *[
            client.post("/api/v1/purchases/customer-stock", json=body, headers=headers)
            for _ in range(2)
        ]
    )
    assert [r.status_code for r in results] == [201, 201]
    assert results[0].json() == results[1].json()
    assert results[0].json()["source"] == "customer"
    assert results[0].json()["supplier_id"] is None
    summary = (
        await client.get("/api/v1/cash/summary", params={"location_id": s["location"]})
    ).json()
    assert Decimal(summary["customer_purchases_usd"]) == 250
    assert Decimal(summary["net_usd"]) == 750
    async with test_session_factory() as db:
        assert (
            await db.scalar(
                select(InventoryBalance.total_weight).where(InventoryBalance.purity_id == s["p18"])
            )
            == 105
        )
        assert await db.scalar(select(func.count()).select_from(SupplierLedgerEntry)) == 0
    failed = await client.post(
        "/api/v1/purchases/customer-stock",
        json={**body, "paid_usd": "900"},
        headers={**cashier, "Idempotency-Key": "too-much"},
    )
    assert failed.status_code == 409
    async with test_session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(Purchase)) == 1
    employee = await headers_for(test_session_factory, "employee")
    assert (
        await client.post(
            "/api/v1/purchases/customer-stock",
            json=body,
            headers={**employee, "Idempotency-Key": "employee"},
        )
    ).status_code == 403


async def test_purchase_photo_attachment_and_replay(
    client, test_session_factory, tmp_path, monkeypatch
):
    from app.api.v1.item_photos import settings

    monkeypatch.setattr(settings, "item_image_dir", str(tmp_path))
    s = await setup_shop(client, test_session_factory)
    picture = io.BytesIO()
    Image.new("RGB", (20, 20), "red").save(picture, format="PNG")
    staged = await client.post("/api/v1/purchases/photos", content=picture.getvalue())
    assert staged.status_code == 201, staged.text
    body = invoice(s)
    body["items"][0]["photo_token"] = staged.json()["token"]
    headers = {"Idempotency-Key": "with-photo"}
    response = await client.post("/api/v1/purchases/item", json=body, headers=headers)
    assert response.status_code == 201, response.text
    assert (
        await client.post("/api/v1/purchases/item", json=body, headers=headers)
    ).json() == response.json()
    items = (
        await client.get("/api/v1/inventory/items", params={"purchase_id": response.json()["id"]})
    ).json()
    assert items[0]["image_url"] == staged.json()["image_url"]
    assert (await client.get(items[0]["image_url"])).status_code == 200
    assert (await client.post("/api/v1/purchases/item", json=body)).status_code == 409
    async with test_session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(InventoryItem)) == 2


async def test_invalid_cash_substitution_and_unfunded_payment_leave_debt_unchanged(
    client, test_session_factory
):
    s = await setup_shop(client, test_session_factory)
    await client.post("/api/v1/purchases/item", json=invoice(s))
    url = f"/api/v1/suppliers/{s['supplier']}"
    before = (await client.get(url + "/balance")).json()
    body = {
        "idempotency_key": "invalid",
        "direction": "sent",
        "location_id": s["location"],
        "cash_gold_usd": "100",
    }
    assert (await client.post(url + "/settlements", json=body)).status_code == 422
    assert (
        await client.post(
            url + "/settlements", json={**body, "cash_gold_usd": "1100", "gold_price_usd": "80"}
        )
    ).status_code == 409
    assert (await client.get(url + "/balance")).json() == before


async def test_supplier_items_use_one_live_quote_and_invoice_ledger_total(
    client, test_session_factory, monkeypatch
):
    from app.services import purchase_service

    s = await setup_shop(client, test_session_factory)
    calls = []
    quote_time = datetime.now(UTC).isoformat()

    async def quote():
        calls.append(True)
        return {"gram_24k_usd": "100.5", "fetched_at": quote_time, "stale": False}

    monkeypatch.setattr(purchase_service, "get_quote", quote)
    body = {
        "supplier_id": s["supplier"],
        "location_id": s["location"],
        "total_gold_charge_grams": "100",
        "items": [
            {
                "supplier_id": s["supplier"],
                "product_id": s["item18"],
                "weight": "10",
                "making_charge": "5",
                "gold_price_per_gram": "0.0001",
            }
            for _ in range(10)
        ],
    }
    headers = {"Idempotency-Key": "ten-pieces"}
    response = await client.post("/api/v1/purchases/item", json=body, headers=headers)
    assert response.status_code == 201, response.text
    assert datetime.fromisoformat(
        response.json()["gold_quote_at"].replace("Z", "+00:00")
    ) == datetime.fromisoformat(quote_time)
    lines = (await client.get(f"/api/v1/purchases/items/{response.json()['id']}")).json()
    assert len(lines) == 10
    assert {Decimal(line["gold_price_per_gram"]) for line in lines} == {Decimal("75.7538")}
    assert (
        await client.post("/api/v1/purchases/item", json=body, headers=headers)
    ).json() == response.json()
    assert len(calls) == 1
    async with test_session_factory() as db:
        ledger = list(await db.scalars(select(SupplierLedgerEntry)))
        assert len(ledger) == 1
        assert ledger[0].gold_24k == Decimal("75.377")
        assert ledger[0].making_usd == 50
        assert await db.scalar(select(func.count()).select_from(InventoryItem)) == 10
        assert (
            await db.scalar(
                select(InventoryBalance.total_weight).where(InventoryBalance.purity_id == s["p18"])
            )
            == 100
        )


async def test_mixed_karats_are_priced_from_the_same_quote(client, test_session_factory):
    s = await setup_shop(client, test_session_factory)
    response = await client.post("/api/v1/purchases/item", json=invoice(s))
    assert response.status_code == 201
    lines = (await client.get(f"/api/v1/purchases/items/{response.json()['id']}")).json()
    assert [Decimal(line["gold_price_per_gram"]) for line in lines] == [
        Decimal("75.7538"),
        Decimal("88.3794"),
    ]


@pytest.mark.parametrize("failure", ["stale", "unavailable"])
async def test_missing_fresh_quote_cannot_create_invoice(
    client, test_session_factory, monkeypatch, failure
):
    from fastapi import HTTPException

    from app.models.operationReceipt import OperationReceipt
    from app.services import purchase_service

    s = await setup_shop(client, test_session_factory)

    async def quote():
        if failure == "unavailable":
            raise HTTPException(503, "Gold quote unavailable")
        return {"gram_24k_usd": "100", "fetched_at": datetime.now(UTC).isoformat(), "stale": True}

    monkeypatch.setattr(purchase_service, "get_quote", quote)
    response = await client.post("/api/v1/purchases/item", json=invoice(s))
    assert response.status_code == 503
    async with test_session_factory() as db:
        for model in [Purchase, InventoryItem, SupplierLedgerEntry, OperationReceipt]:
            assert await db.scalar(select(func.count()).select_from(model)) == 0


async def test_zero_usd_opening_inventory_works_with_empty_drawer_and_retries(
    client, test_session_factory
):
    from sqlalchemy import delete

    from app.models.purchaseStock import PurchaseStock

    s = await setup_shop(client, test_session_factory)
    async with test_session_factory() as db:
        await db.execute(delete(CashEntry))
        await db.execute(delete(InventoryBalance))
        await db.commit()
    cashier = await headers_for(test_session_factory, "cashier")
    headers = {**cashier, "Idempotency-Key": "opening-gold"}
    body = {
        "location_id": s["location"],
        "product_id": s["bulk"],
        "weight": "12.345",
        "paid_usd": "0",
        "placement": "factory",
        "notes": "Opening stock",
    }
    responses = await asyncio.gather(
        *[
            client.post("/api/v1/purchases/customer-stock", json=body, headers=headers)
            for _ in range(2)
        ]
    )
    assert [r.status_code for r in responses] == [201, 201]
    assert responses[0].json() == responses[1].json()
    assert responses[0].json()["source"] == "opening"
    assert Decimal(responses[0].json()["paid_usd"]) == 0
    async with test_session_factory() as db:
        assert await db.scalar(select(InventoryBalance.total_weight)) == Decimal("12.345")
        assert await db.scalar(select(PurchaseStock.cost_per_gram)) == 0
        assert await db.scalar(select(func.count()).select_from(CashEntry)) == 0
        assert await db.scalar(select(func.count()).select_from(SupplierLedgerEntry)) == 0
    negative = await client.post(
        "/api/v1/purchases/customer-stock",
        json={**body, "paid_usd": "-1"},
        headers={**cashier, "Idempotency-Key": "negative"},
    )
    assert negative.status_code == 422
