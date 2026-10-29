from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import GoldPurity, Purchase, Sale, SupplierLedgerEntry
from app.models.cashLedger import CashEntry
from app.services.supplier_ledger_service import post_entry
from tests.api.test_auth import login_user
from tests.api.test_purchase import test_create_purchase_stock as create_stock_purchase

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def seed_cash(factory, purchase, amount="100"):
    """Seed a recorded customer cash receipt for settlement tests."""
    async with factory() as db:
        sale = Sale(location_id=purchase.location_id, created_by=purchase.created_by)
        db.add(sale)
        await db.flush()
        db.add(
            CashEntry(
                location_id=purchase.location_id,
                sale_id=sale.id,
                kind="sale",
                amount_usd=Decimal(amount),
                created_by=purchase.created_by,
            )
        )
        await db.commit()


async def test_purchase_and_partial_settlements(client, test_session_factory):
    purchase_response = await create_stock_purchase(client, test_session_factory)
    async with test_session_factory() as db:
        purchase = await db.get(Purchase, purchase_response.json()["id"])
        entry = await db.scalar(
            select(SupplierLedgerEntry).where(SupplierLedgerEntry.purchase_id == purchase.id)
        )
        assert entry.gold_grams == Decimal("2.600")
        supplier_id, purity_id = purchase.supplier_id, entry.purity_id
    tokens = await login_user(client)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    url = f"/api/v1/suppliers/{supplier_id}"
    first = {
        "idempotency_key": "first",
        "location_id": purchase.location_id,
        "direction": "sent",
        "purity_id": purity_id,
        "gold_grams": "1.100",
        "making_usd": "0",
    }
    response = await client.post(f"{url}/settlements", json=first, headers=headers)
    assert response.status_code == 201, response.text
    assert Decimal(response.json()["gold_grams_by_purity"][str(purity_id)]) == Decimal("1.500")
    assert (await client.post(f"{url}/settlements", json=first, headers=headers)).status_code == 409
    second = {**first, "idempotency_key": "second", "gold_grams": "0.500"}
    assert (
        await client.post(f"{url}/settlements", json=second, headers=headers)
    ).status_code == 201
    balance = (await client.get(f"{url}/balance", headers=headers)).json()
    assert Decimal(balance["gold_grams_by_purity"][str(purity_id)]) == Decimal("1.000")
    assert Decimal(balance["making_usd"]) == 0
    assert (await client.get(f"{url}/balance", headers={"Authorization": ""})).status_code == 401


async def test_purities_are_not_nettted_and_usd_is_separate(client, test_session_factory):
    purchase_response = await create_stock_purchase(client, test_session_factory)
    async with test_session_factory() as db:
        purchase = await db.get(Purchase, purchase_response.json()["id"])
        purity = GoldPurity(name="22K", karat=22, purity=91.6)
        db.add(purity)
        await db.flush()
        post_entry(
            db,
            supplier_id=purchase.supplier_id,
            purity_id=purity.id,
            gold_grams=-2,
            making_usd=-10,
            source_key="test-sale",
            kind="sale",
            created_by=purchase.created_by,
        )
        await db.commit()
        supplier_id, purity_id = purchase.supplier_id, purity.id
    tokens = await login_user(client)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    url = f"/api/v1/suppliers/{supplier_id}"
    balance = (await client.get(f"{url}/balance", headers=headers)).json()
    assert len(balance["gold_grams_by_purity"]) == 2
    assert Decimal(balance["gold_grams_by_purity"][str(purity_id)]) == -2
    assert Decimal(balance["making_usd"]) == -10
    payment = {
        "idempotency_key": "usd",
        "direction": "received",
        "making_usd": "5.25",
        "location_id": purchase.location_id,
    }
    result = await client.post(f"{url}/settlements", json=payment, headers=headers)
    assert result.status_code == 201
    assert Decimal(result.json()["making_usd"]) == Decimal("-4.75")
    assert result.json()["gold_grams_by_purity"] == balance["gold_grams_by_purity"]
    invalid = {"idempotency_key": "invalid", "direction": "sent", "gold_grams": "1"}
    assert (
        await client.post(f"{url}/settlements", json=invalid, headers=headers)
    ).status_code == 422
    assert (
        await client.post(
            f"{url}/settlements", json={**payment, "making_usd": "-1"}, headers=headers
        )
    ).status_code == 422


async def test_invoice_authorship_and_supplier_consistency(client, test_session_factory):
    from tests.api.test_purchase import test_create_purchase as create_item_purchase

    response, _, _ = await create_item_purchase(client, test_session_factory)
    async with test_session_factory() as db:
        purchase = await db.get(Purchase, response.json()["id"])
        original_actor = purchase.created_by
    tokens = await login_user(client)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    me = (await client.get("/api/v1/users/me", headers=headers)).json()
    assert original_actor != me["id"]
    # A supplier mismatch is rejected before any invoice is persisted.
    payload = {
        "supplier_id": purchase.supplier_id,
        "created_by": original_actor,
        "location_id": purchase.location_id,
        "items": [
            {
                "supplier_id": 2147483647,
                "product_id": 1,
                "weight": 1,
                "gold_price_per_gram": 10,
                "gold_charge_in_grams": 1,
                "making_charge": 1,
                "barcode": "MISMATCH",
            }
        ],
    }
    assert (
        await client.post("/api/v1/purchases/item", json=payload, headers=headers)
    ).status_code == 422

    from app.models import PurchaseItem

    async with test_session_factory() as db:
        line = await db.scalar(select(PurchaseItem).where(PurchaseItem.purchase_id == purchase.id))
        product_id = line.product_id
    payload["items"][0].update(supplier_id=purchase.supplier_id, product_id=product_id)
    response = await client.post("/api/v1/purchases/item", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    assert response.json()["created_by"] == me["id"]


async def test_history_and_settlement_reversal(client, test_session_factory):
    purchase_response = await create_stock_purchase(client, test_session_factory)
    async with test_session_factory() as db:
        purchase = await db.get(Purchase, purchase_response.json()["id"])
        entry = await db.scalar(
            select(SupplierLedgerEntry).where(SupplierLedgerEntry.purchase_id == purchase.id)
        )
        supplier_id, purity_id = purchase.supplier_id, entry.purity_id
    await seed_cash(test_session_factory, purchase)
    url = f"/api/v1/suppliers/{supplier_id}"
    payment = {
        "idempotency_key": "reverse-me",
        "direction": "sent",
        "purity_id": purity_id,
        "gold_grams": "1",
        "making_usd": "3.50",
        "location_id": purchase.location_id,
    }
    assert (await client.post(f"{url}/settlements", json=payment)).status_code == 201
    cash = (
        await client.get("/api/v1/cash/summary", params={"location_id": purchase.location_id})
    ).json()
    assert Decimal(cash["net_usd"]) == Decimal("96.50")
    history = await client.get(f"{url}/ledger", params={"kind": "settlement", "limit": 1})
    assert history.status_code == 200
    assert history.headers["X-Total-Count"] == "1"
    settlement = history.json()[0]
    assert Decimal(settlement["gold_grams"]) == -1
    reversal = await client.post(
        f"{url}/ledger/{settlement['id']}/reverse",
        json={"idempotency_key": "reverse-1", "reason": "Entered in error"},
    )
    assert reversal.status_code == 201, reversal.text
    assert reversal.json()["reversal_of_id"] == settlement["id"]
    assert Decimal(reversal.json()["gold_grams"]) == 1
    assert Decimal(reversal.json()["making_usd"]) == Decimal("3.50")
    assert (
        await client.post(
            f"{url}/ledger/{settlement['id']}/reverse",
            json={"idempotency_key": "reverse-2", "reason": "Duplicate"},
        )
    ).status_code == 409
    balance = (await client.get(f"{url}/balance")).json()
    assert Decimal(balance["gold_grams_by_purity"][str(purity_id)]) == Decimal("2.600")
    assert Decimal(balance["making_usd"]) == 0
    cash = (
        await client.get("/api/v1/cash/summary", params={"location_id": purchase.location_id})
    ).json()
    assert Decimal(cash["net_usd"]) == 100
    all_entries = await client.get(f"{url}/ledger", params={"limit": 1, "offset": 1})
    assert all_entries.headers["X-Total-Count"] == "3"
    assert all_entries.json()[0]["id"] == settlement["id"]
    assert (
        await client.post(
            f"{url}/ledger/{entry.id}/reverse",
            json={"idempotency_key": "wrong", "reason": "Cannot reverse invoice here"},
        )
    ).status_code == 409


async def test_usd_settlement_requires_cash_location_and_duplicate_is_atomic(
    client, test_session_factory
):
    import asyncio

    from sqlalchemy import func

    from app.models.cashLedger import CashEntry

    purchase_response = await create_stock_purchase(client, test_session_factory)
    async with test_session_factory() as db:
        purchase = await db.get(Purchase, purchase_response.json()["id"])
        supplier_id, location_id = purchase.supplier_id, purchase.location_id
    await seed_cash(test_session_factory, purchase)
    url = f"/api/v1/suppliers/{supplier_id}/settlements"
    payload = {"idempotency_key": "concurrent-payment", "direction": "sent", "making_usd": "10"}
    assert (await client.post(url, json=payload)).status_code == 422
    payload["location_id"] = location_id
    responses = await asyncio.gather(client.post(url, json=payload), client.post(url, json=payload))
    assert sorted(response.status_code for response in responses) == [201, 409]
    async with test_session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(CashEntry)) == 2
    summary = (await client.get("/api/v1/cash/summary", params={"location_id": location_id})).json()
    assert Decimal(summary["net_usd"]) == 90
