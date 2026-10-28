import asyncio
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.main import app
from app.models import InventoryBalance, InventoryItem, Purchase, PurchaseItem, StockTransferRecord
from app.models.operationReceipt import OperationReceipt
from app.models.supplierLedger import SupplierLedgerEntry
from tests.api.test_purchase import test_create_purchase as create_purchase
from tests.api.test_purchase import test_create_purchase_stock as create_stock_purchase

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def purchase_payload(client, factory):
    existing, _, _ = await create_purchase(client, factory)
    async with factory() as db:
        purchase = await db.get(Purchase, existing.json()["id"])
        line = await db.scalar(select(PurchaseItem).where(PurchaseItem.purchase_id == purchase.id))
        return {
            "supplier_id": purchase.supplier_id,
            "location_id": purchase.location_id,
            "items": [
                {
                    "supplier_id": purchase.supplier_id,
                    "product_id": line.product_id,
                    "weight": "1.000",
                    "gold_price_per_gram": "100.00",
                    "gold_charge_in_grams": "1",
                    "making_charge": "5",
                }
            ],
        }


async def test_purchase_retries_are_atomic_and_return_original_result(client, test_session_factory):
    payload = await purchase_payload(client, test_session_factory)
    headers = {"Idempotency-Key": "purchase-retry"}
    responses = await asyncio.gather(
        *[client.post("/api/v1/purchases/item", json=payload, headers=headers) for _ in range(2)]
    )
    assert [r.status_code for r in responses] == [201, 201]
    assert responses[0].json() == responses[1].json()
    # Decimal formatting and ignored authorship must not turn a retry into a new operation.
    payload["items"][0]["weight"] = "1.0"
    payload["created_by"] = 2147483647
    retry = await client.post("/api/v1/purchases/item", json=payload, headers=headers)
    assert retry.json() == responses[0].json()
    payload["items"][0]["weight"] = "2"
    assert (
        await client.post("/api/v1/purchases/item", json=payload, headers=headers)
    ).status_code == 409
    async with test_session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(Purchase)) == 2
        assert await db.scalar(select(func.count()).select_from(InventoryItem)) == 2
        assert await db.scalar(select(func.count()).select_from(SupplierLedgerEntry)) == 2


async def test_failed_purchase_rolls_back_key_and_can_be_corrected(client, test_session_factory):
    payload = await purchase_payload(client, test_session_factory)
    valid_product = payload["items"][0]["product_id"]
    payload["items"][0]["product_id"] = 2147483647
    headers = {"Idempotency-Key": "correct-me"}
    assert (
        await client.post("/api/v1/purchases/item", json=payload, headers=headers)
    ).status_code == 409
    async with test_session_factory() as db:
        assert (
            await db.scalar(select(OperationReceipt.id).where(OperationReceipt.key == "correct-me"))
            is None
        )
    payload["items"][0]["product_id"] = valid_product
    assert (
        await client.post("/api/v1/purchases/item", json=payload, headers=headers)
    ).status_code == 201


async def test_stock_transfer_replay_does_not_move_gold_twice(client, test_session_factory):
    purchase = await create_stock_purchase(client, test_session_factory)
    location_id = purchase.json()["location_id"]
    async with test_session_factory() as db:
        balance = await db.scalar(select(InventoryBalance))
        purity_id = balance.purity_id
    payload = {
        "purity_id": purity_id,
        "source_location_id": location_id,
        "destination_location_id": location_id,
        "source_placement": "factory",
        "destination_placement": "showroom",
        "weight": "1.000",
    }
    headers = {"Idempotency-Key": "transfer-retry"}
    responses = await asyncio.gather(
        *[
            client.post("/api/v1/inventory/stocks/transfer", json=payload, headers=headers)
            for _ in range(2)
        ]
    )
    assert [r.status_code for r in responses] == [200, 200]
    assert responses[0].json() == responses[1].json()
    async with test_session_factory() as db:
        balances = {b.placement: b.total_weight for b in await db.scalars(select(InventoryBalance))}
        assert balances == {"factory": Decimal("1.600"), "showroom": Decimal("1.000")}
        assert await db.scalar(select(func.count()).select_from(StockTransferRecord)) == 1
    payload["weight"] = "0.5"
    changed = await client.post("/api/v1/inventory/stocks/transfer", json=payload)
    assert changed.status_code == 200
    payload["weight"] = "1"
    replay = await client.post("/api/v1/inventory/stocks/transfer", json=payload, headers=headers)
    assert replay.json() == responses[0].json()


async def test_new_operations_require_idempotency_header(client, test_session_factory):
    payload = await purchase_payload(client, test_session_factory)
    # A raw client does not have the test convenience hook which assigns new operation keys.
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": client.headers["Authorization"]},
    ) as raw:
        for path in [
            "/api/v1/purchases/item",
            "/api/v1/purchases/stock",
            "/api/v1/inventory/stocks/transfer",
        ]:
            response = await raw.post(path, json=payload)
            assert response.status_code == 422
            assert any(e["loc"] == ["header", "Idempotency-Key"] for e in response.json()["detail"])


async def test_bulk_purchase_retry_preserves_single_balance_increment(client, test_session_factory):
    from app.models import PurchaseStock

    existing = await create_stock_purchase(client, test_session_factory)
    async with test_session_factory() as db:
        invoice = await db.get(Purchase, existing.json()["id"])
        stock = await db.scalar(
            select(PurchaseStock).where(PurchaseStock.purchase_id == invoice.id)
        )
        payload = {
            "supplier_id": invoice.supplier_id,
            "location_id": invoice.location_id,
            "item": {
                "product_id": stock.product_id,
                "stock_for": "factory",
                "weight": "2.600",
                "cost_per_gram": "55.05",
            },
        }
    headers = {"Idempotency-Key": "bulk-purchase-retry"}
    responses = await asyncio.gather(
        *[client.post("/api/v1/purchases/stock", json=payload, headers=headers) for _ in range(2)]
    )
    assert [r.status_code for r in responses] == [201, 201]
    assert responses[0].json() == responses[1].json()
    payload["item"]["making_charge"] = "0.00"
    assert (
        await client.post("/api/v1/purchases/stock", json=payload, headers=headers)
    ).json() == responses[0].json()
    async with test_session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(Purchase)) == 2
        assert await db.scalar(select(func.sum(InventoryBalance.total_weight))) == Decimal("5.200")
        assert await db.scalar(select(func.count()).select_from(SupplierLedgerEntry)) == 2
