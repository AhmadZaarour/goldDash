"""Validate form inputs and enforce active trading entities without side effects."""

from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.models import (
    CashEntry,
    Customer,
    Product,
    Purchase,
    PurchaseItem,
    Sale,
    SupplierLedgerEntry,
)
from tests.api.test_purchase import test_create_purchase as create_purchase

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.mark.parametrize(
    "field,value",
    [
        ("username", ""),
        ("username", "   "),
        ("username", "u" * 51),
        ("password", ""),
        ("password", "short"),
        ("password", " " * 8),
        ("password", "x" * 129),
    ],
)
async def test_registration_rejects_invalid_credentials(client, field, value):
    payload = {
        "email": f"{uuid4().hex}@example.com",
        "username": uuid4().hex,
        "password": "ValidTestPassword123!",
        field: value,
    }
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "x" * 51, "phone": "123"},
        {"name": "   ", "phone": "123"},
        {"name": "Customer", "phone": "x" * 51},
    ],
)
async def test_customer_validation_matches_database(client, test_session_factory, payload):
    assert (await client.post("/api/v1/customers", json=payload)).status_code == 422
    async with test_session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(Customer)) == 0


async def test_supplier_phone_only_patch_and_inactive_creation(client):
    created = await client.post(
        "/api/v1/suppliers", json={"name": "Inactive supplier", "phone": "123", "is_active": False}
    )
    assert created.status_code == 201
    assert created.json()["is_active"] is False
    url = f"/api/v1/suppliers/{created.json()['id']}"
    patched = await client.patch(url, json={"phone": "456"})
    assert patched.status_code == 200
    assert patched.json()["phone"] == "456"
    assert patched.json()["is_active"] is False
    for payload in [{"name": None}, {"phone": None}, {"is_active": None}, {"phone": "x" * 21}]:
        assert (await client.patch(url, json=payload)).status_code == 422
    assert (await client.get(url)).json() == patched.json()


async def test_location_nullability_and_creation_flag(client):
    created = await client.post(
        "/api/v1/locations",
        json={"name": "Closed shop", "code": "CLOSED", "address": "Old street", "is_active": False},
    )
    assert created.status_code == 201
    assert created.json()["is_active"] is False
    url = f"/api/v1/locations/{created.json()['id']}"
    for payload in [{"name": None}, {"code": None}, {"is_active": None}, {"address": "x" * 201}]:
        assert (await client.patch(url, json=payload)).status_code == 422
    updated = await client.patch(url, json={"address": None})
    assert updated.status_code == 200
    assert updated.json()["address"] is None
    assert updated.json()["name"] == "Closed shop"
    assert updated.json()["is_active"] is False


async def test_customer_partial_patch_and_nullable_phone(client):
    created = await client.post("/api/v1/customers", json={"name": "Customer", "phone": "123"})
    assert created.status_code == 201
    url = f"/api/v1/customers/{created.json()['id']}"
    updated = await client.patch(url, json={"phone": "456"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "Customer"
    assert updated.json()["phone"] == "456"
    assert (await client.patch(url, json={"name": None})).status_code == 422
    assert (await client.patch(url, json={"phone": None})).json()["phone"] is None
    no_phone = await client.post("/api/v1/customers", json={"name": "Walk-in contact"})
    assert no_phone.status_code == 201
    assert no_phone.json()["phone"] is None


async def purchase_payloads(client, test_session_factory):
    invoice, _, inventory = await create_purchase(client, test_session_factory)
    async with test_session_factory() as db:
        purchase = await db.get(Purchase, invoice.json()["id"])
        line = await db.scalar(select(PurchaseItem).where(PurchaseItem.purchase_id == purchase.id))
        item_product = await db.get(Product, line.product_id)
        bulk = Product(
            sku=f"BULK-{uuid4().hex}",
            name="Bulk gold",
            category_id=item_product.category_id,
            purity_id=item_product.purity_id,
            inventory_type="bulk",
        )
        db.add(bulk)
        await db.commit()
        header = {"supplier_id": purchase.supplier_id, "location_id": purchase.location_id}
        item_payload = {
            **header,
            "items": [
                {
                    "supplier_id": purchase.supplier_id,
                    "product_id": line.product_id,
                    "weight": "1",
                    "gold_price_per_gram": "100",
                    "gold_charge_in_grams": "1",
                    "making_charge": "5",
                }
            ],
        }
        stock_payload = {
            **header,
            "item": {
                "product_id": bulk.id,
                "stock_for": "factory",
                "weight": "1",
                "cost_per_gram": "100",
            },
        }
    return item_payload, stock_payload, inventory.json()["id"]


async def test_inactive_locations_reject_new_purchases_sales_and_cash_settlements(
    client, test_session_factory
):
    item_payload, stock_payload, item_id = await purchase_payloads(client, test_session_factory)
    location_id = item_payload["location_id"]
    assert (
        await client.patch(f"/api/v1/locations/{location_id}", json={"is_active": False})
    ).status_code == 200
    for kind, payload in [("item", item_payload), ("stock", stock_payload)]:
        response = await client.post(f"/api/v1/purchases/{kind}", json=payload)
        assert response.status_code == 409, response.text
        assert "inactive" in response.json()["detail"]
    sale = {
        "location_id": location_id,
        "items": [
            {
                "inventory_item_id": item_id,
                "gold_price_per_gram": "100",
                "discount": "0",
                "sell_price": "100",
            }
        ],
    }
    assert (await client.post("/api/v1/sales/item", json=sale)).status_code == 409
    settlement = {
        "idempotency_key": "inactive-drawer",
        "direction": "sent",
        "location_id": location_id,
        "making_usd": "1",
    }
    assert (
        await client.post(
            f"/api/v1/suppliers/{item_payload['supplier_id']}/settlements", json=settlement
        )
    ).status_code == 409
    async with test_session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(Purchase)) == 1
        assert await db.scalar(select(func.count()).select_from(Sale)) == 0
        assert await db.scalar(select(func.count()).select_from(CashEntry)) == 0


async def test_inactive_supplier_rejects_purchases_bulk_sales_and_settlements(
    client, test_session_factory
):
    item_payload, stock_payload, _ = await purchase_payloads(client, test_session_factory)
    supplier_id = item_payload["supplier_id"]
    assert (
        await client.patch(f"/api/v1/suppliers/{supplier_id}", json={"is_active": False})
    ).status_code == 200
    for kind, payload in [("item", item_payload), ("stock", stock_payload)]:
        assert (await client.post(f"/api/v1/purchases/{kind}", json=payload)).status_code == 409
    async with test_session_factory() as db:
        product = await db.get(Product, stock_payload["item"]["product_id"])
        purity_id = product.purity_id
    bulk_sale = {
        "location_id": item_payload["location_id"],
        "item": {
            "supplier_id": supplier_id,
            "gold_purity_id": purity_id,
            "weight": "1",
            "gold_charge_in_grams": "1",
            "making_charge": "5",
        },
    }
    response = await client.post("/api/v1/sales/stock", json=bulk_sale)
    assert response.status_code == 409
    assert "inactive" in response.json()["detail"]
    settlement = {
        "idempotency_key": "inactive-supplier",
        "location_id": item_payload["location_id"],
        "direction": "sent",
        "purity_id": purity_id,
        "gold_grams": "1",
    }
    assert (
        await client.post(f"/api/v1/suppliers/{supplier_id}/settlements", json=settlement)
    ).status_code == 409
    assert (await client.get(f"/api/v1/suppliers/{supplier_id}/balance")).status_code == 200
    assert (await client.get(f"/api/v1/suppliers/{supplier_id}/ledger")).status_code == 200
    async with test_session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(Purchase)) == 1
        assert await db.scalar(select(func.count()).select_from(SupplierLedgerEntry)) == 1
