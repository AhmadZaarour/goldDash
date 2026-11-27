from decimal import Decimal

import pytest

from app.models import Category, GoldPurity, Product, Supplier, SupplierLedgerEntry
from app.models.goldPriceSettings import GoldPriceSettings
from tests.api.test_backend_access import headers_for

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_catalog_deletion_blocks_referenced_records(client, test_session_factory):
    async with test_session_factory() as db:
        category = Category(name="Chains")
        purity = GoldPurity(name="18k", karat=18, purity=Decimal(75))
        db.add_all([category, purity])
        await db.flush()
        product = Product(
            sku="C-01",
            name="Chain",
            category_id=category.id,
            purity_id=purity.id,
            inventory_type="item",
        )
        db.add(product)
        await db.commit()

    category_url = f"/api/v1/categories/{category.id}"
    purity_url = f"/api/v1/goldpurities/{purity.id}"
    employee = await headers_for(test_session_factory, "employee")
    assert (await client.delete(category_url, headers=employee)).status_code == 403
    assert (await client.delete(category_url)).status_code == 409
    assert (await client.patch(purity_url, json={"purity": "76"})).status_code == 409
    assert (await client.delete(purity_url)).status_code == 409

    assert (await client.delete(f"/api/v1/products/{product.id}")).status_code == 204
    assert (await client.delete(category_url)).status_code == 204
    assert (await client.delete(purity_url)).status_code == 204
    assert (await client.get(category_url)).status_code == 404
    assert (await client.get("/api/v1/admin/data")).status_code == 404


async def test_staff_admin_actions_respect_history_and_account_permissions(
    client, test_session_factory
):
    employee = await headers_for(test_session_factory, "employee")
    account = (await client.get("/api/v1/users/me", headers=employee)).json()
    url = f"/api/v1/operations/staff/{account['id']}"
    assert (await client.patch(url, json={"is_active": False}, headers=employee)).status_code == 403
    assert (await client.patch(url, json={"role": "admin"})).status_code == 409
    edited = await client.patch(
        url, json={"username": "cashier-example", "role": "cashier", "workspace_access": "both"}
    )
    assert edited.status_code == 200
    assert edited.json()["username"] == "cashier-example"
    assert edited.json()["role"] == "cashier"

    async with test_session_factory() as db:
        db.add(GoldPriceSettings(unit="showroom", updated_by=account["id"]))
        await db.commit()
    assert (await client.delete(url)).status_code == 409
    assert (await client.patch(url, json={"is_active": False})).status_code == 200
    assert (await client.get("/api/v1/users/me", headers=employee)).status_code == 403

    admin = (await client.get("/api/v1/users/me")).json()
    assert (await client.delete(f"/api/v1/operations/staff/{admin['id']}")).status_code == 409


async def test_supplier_settlement_note_edit_preserves_balances(client, test_session_factory):
    admin = (await client.get("/api/v1/users/me")).json()
    async with test_session_factory() as db:
        supplier = Supplier(name="Workshop", phone="12345", is_active=True)
        db.add(supplier)
        await db.flush()
        entry = SupplierLedgerEntry(
            supplier_id=supplier.id,
            source_key="test-settlement",
            kind="settlement",
            gold_grams=Decimal(0),
            gold_24k=Decimal(0),
            valuation_factor=Decimal(1),
            making_usd=Decimal(-10),
            created_by=admin["id"],
            unit="factory",
        )
        db.add(entry)
        await db.commit()

    url = f"/api/v1/suppliers/{supplier.id}/ledger/{entry.id}"
    assert (await client.patch(url, json={"note": "Corrected"})).status_code == 404
    headers = {"X-Business-Unit": "factory"}
    assert (
        await client.patch(url, json={"note": "Corrected", "making_usd": 0}, headers=headers)
    ).status_code == 422
    result = await client.patch(url, json={"note": "Corrected"}, headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["note"] == "Corrected"
    assert Decimal(result.json()["making_usd"]) == Decimal(-10)
    assert (await client.delete(f"/api/v1/suppliers/{supplier.id}")).status_code == 409
