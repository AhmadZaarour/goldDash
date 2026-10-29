import asyncio
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models import GoldPurity, Purchase, Supplier, SupplierLedgerEntry
from app.models.cashLedger import CashEntry
from app.models.inventoryBalance import InventoryBalance
from app.services.supplier_ledger_service import post_entry
from tests.api.test_purchase import test_create_purchase_stock as stock_purchase
from tests.api.test_supplier_ledger import seed_cash

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def account(client, factory):
    result = await stock_purchase(client, factory)
    async with factory() as db:
        purchase = await db.get(Purchase, result.json()["id"])
        balance = await db.scalar(
            select(InventoryBalance).where(InventoryBalance.location_id == purchase.location_id)
        )
        purity_id = balance.purity_id
    return purchase, purity_id, f"/api/v1/suppliers/{purchase.supplier_id}"


async def test_cash_shortage_rolls_back_gold_and_ledger(client, test_session_factory):
    purchase, purity, url = await account(client, test_session_factory)
    payload = dict(
        idempotency_key="short-cash",
        direction="sent",
        location_id=purchase.location_id,
        purity_id=purity,
        gold_grams="1",
        making_usd="1",
    )
    response = await client.post(url + "/settlements", json=payload)
    assert response.status_code == 409
    assert "cash" in response.json()["detail"]
    async with test_session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(CashEntry)) == 0
        assert await db.scalar(select(func.count()).select_from(SupplierLedgerEntry)) == 1
        assert await db.scalar(select(InventoryBalance.total_weight)) == Decimal("2.600")
    # The rejected key can be retried once the drawer has funds.
    await seed_cash(test_session_factory, purchase)
    assert (await client.post(url + "/settlements", json=payload)).status_code == 201
    async with test_session_factory() as db:
        assert await db.scalar(select(InventoryBalance.total_weight)) == Decimal("1.600")


async def test_gold_shortage_and_bucket_selection(client, test_session_factory):
    purchase, purity, url = await account(client, test_session_factory)
    payload = dict(
        idempotency_key="short-gold",
        direction="sent",
        location_id=purchase.location_id,
        purity_id=purity,
        gold_grams="2.601",
        making_usd="0",
    )
    assert (await client.post(url + "/settlements", json=payload)).status_code == 409
    payload.update(gold_grams="1", placement="showroom")
    assert (await client.post(url + "/settlements", json=payload)).status_code == 409
    response = await client.get(url + "/availability", params={"location_id": purchase.location_id})
    assert response.json() == {"cash_usd": "0", "gold_grams_by_purity": {str(purity): "2.600"}}
    payload["placement"] = "factory"
    assert (await client.post(url + "/settlements", json=payload)).status_code == 201
    assert (
        await client.post(url + "/settlements", json={**payload, "location_id": None})
    ).status_code == 422


async def test_full_settlement_requires_all_units_zero_and_reopens(client, test_session_factory):
    purchase, purity, url = await account(client, test_session_factory)
    async with test_session_factory() as db:
        other = GoldPurity(name="22K", karat=22, purity=91.6)
        db.add(other)
        await db.flush()
        other_id = other.id
        post_entry(
            db,
            supplier_id=purchase.supplier_id,
            purity_id=other.id,
            gold_grams=-1,
            making_usd=5,
            source_key="other-unit",
            kind="sale",
            created_by=purchase.created_by,
        )
        await db.commit()
    payload = dict(
        idempotency_key="full",
        direction="sent",
        location_id=purchase.location_id,
        purity_id=purity,
        gold_grams="2.600",
        making_usd="0",
        close_account=True,
    )
    assert (await client.post(url + "/settlements", json=payload)).status_code == 409
    payload["close_account"] = False
    result = await client.post(url + "/settlements", json=payload)
    assert result.status_code == 201
    assert result.json()["is_settled"] is False
    # Receiving the other purity does not clear the outstanding USD.
    received = dict(
        idempotency_key="receive",
        direction="received",
        location_id=purchase.location_id,
        purity_id=other_id,
        gold_grams="1",
        making_usd="0",
        close_account=True,
    )
    assert (await client.post(url + "/settlements", json=received)).status_code == 409
    received["close_account"] = False
    assert (await client.post(url + "/settlements", json=received)).status_code == 201
    await seed_cash(test_session_factory, purchase, "5")
    result = await client.post(
        url + "/settlements",
        json=dict(
            idempotency_key="last",
            direction="sent",
            location_id=purchase.location_id,
            making_usd="5",
            close_account=True,
        ),
    )
    assert result.status_code == 201, result.text
    assert result.json()["is_settled"] is True
    async with test_session_factory() as db:
        post_entry(
            db,
            supplier_id=purchase.supplier_id,
            purity_id=purity,
            gold_grams=1,
            making_usd=0,
            source_key="new-trade",
            kind="purchase",
            created_by=purchase.created_by,
        )
        await db.commit()
    assert (await client.get(url + "/balance")).json()["is_settled"] is False


async def test_received_resources_and_reversal_cannot_overdraw(client, test_session_factory):
    purchase, purity, url = await account(client, test_session_factory)
    result = await client.post(
        url + "/settlements",
        json=dict(
            idempotency_key="received",
            direction="received",
            location_id=purchase.location_id,
            purity_id=purity,
            placement="showroom",
            gold_grams="1",
            making_usd="10",
        ),
    )
    assert result.status_code == 201
    ledger = (await client.get(url + "/ledger", params={"kind": "settlement"})).json()[0]
    available = (
        await client.get(
            url + "/availability",
            params={"location_id": purchase.location_id, "placement": "showroom"},
        )
    ).json()
    assert Decimal(available["cash_usd"]) == 10
    assert Decimal(available["gold_grams_by_purity"][str(purity)]) == 1
    # Spend some of the receipt, then reject reversing money we no longer have.
    response = await client.post(
        "/api/v1/cash/outflows",
        json=dict(
            location_id=purchase.location_id, kind="expense", amount_usd="1", description="Expense"
        ),
        headers={"Idempotency-Key": "spend-receipt"},
    )
    assert response.status_code == 201
    reverse = url + f"/ledger/{ledger['id']}/reverse"
    result = await client.post(reverse, json=dict(idempotency_key="reverse", reason="Mistake"))
    assert result.status_code == 409
    await seed_cash(test_session_factory, purchase, "1")
    assert (
        await client.post(reverse, json=dict(idempotency_key="reverse", reason="Mistake"))
    ).status_code == 201
    available = (
        await client.get(
            url + "/availability",
            params={"location_id": purchase.location_id, "placement": "showroom"},
        )
    ).json()
    assert Decimal(available["gold_grams_by_purity"][str(purity)]) == 0
    assert Decimal(available["cash_usd"]) == 0


async def test_concurrent_suppliers_cannot_spend_same_cash(client, test_session_factory):
    purchase, _, url = await account(client, test_session_factory)
    await seed_cash(test_session_factory, purchase, "10")
    async with test_session_factory() as db:
        other = Supplier(name="Other supplier", phone="123456789", is_active=True)
        db.add(other)
        await db.commit()
        other_id = other.id
    payload = dict(
        idempotency_key="concurrent",
        direction="sent",
        location_id=purchase.location_id,
        making_usd="7",
    )
    responses = await asyncio.gather(
        client.post(url + "/settlements", json=payload),
        client.post(f"/api/v1/suppliers/{other_id}/settlements", json=payload),
    )
    assert sorted(r.status_code for r in responses) == [201, 409]
    available = (
        await client.get(url + "/availability", params={"location_id": purchase.location_id})
    ).json()
    assert Decimal(available["cash_usd"]) == 3
