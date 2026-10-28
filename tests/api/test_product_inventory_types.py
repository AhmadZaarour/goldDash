from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.product import Product
from tests.api.test_locations import test_create_location as create_location
from tests.api.test_products import test_create_product as create_product
from tests.api.test_purchase import purchase_payload, purchase_stock_payload
from tests.api.test_suppliers import test_create_supplier as create_supplier

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def references(client, test_session_factory, inventory_type="item"):
    product = await create_product(client, test_session_factory, inventory_type=inventory_type)
    supplier = await create_supplier(client)
    location = await create_location(client)
    me = await client.get("/api/v1/auth/me")
    return product.json(), supplier.json()["id"], location.json()["id"], me.json()["id"]


async def test_product_type_schema_and_partial_update(client, test_session_factory):
    product, _, _, _ = await references(client, test_session_factory)
    url = f"/api/v1/products/{product['id']}"
    invalid_create = {**product, "sku": "INVALID-TYPE", "inventory_type": "anything"}
    assert (await client.post("/api/v1/products", json=invalid_create)).status_code == 422
    assert (await client.patch(url, json={"inventory_type": "anything"})).status_code == 422
    assert (await client.patch(url, json={"inventory_type": None})).status_code == 422
    assert (await client.patch(url, json={"name": None})).status_code == 422
    changed = await client.patch(url, json={"inventory_type": "bulk"})
    assert changed.status_code == 200, changed.text
    assert changed.json()["inventory_type"] == "bulk"
    assert (await client.get(url)).json()["inventory_type"] == "bulk"


@pytest.mark.parametrize("inventory_type", ["item", "bulk"])
async def test_purchase_path_matches_product_type(client, test_session_factory, inventory_type):
    product, supplier_id, location_id, user_id = await references(
        client, test_session_factory, inventory_type
    )
    item_payload = purchase_payload(user_id, location_id, supplier_id, product["id"])
    stock_payload = purchase_stock_payload(user_id, location_id, supplier_id, product["id"])
    matching_path = "item" if inventory_type == "item" else "stock"
    wrong_path = "stock" if inventory_type == "item" else "item"
    payloads = {"item": item_payload, "stock": stock_payload}
    wrong = await client.post(
        f"/api/v1/purchases/{wrong_path}",
        json=payloads[wrong_path],
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert wrong.status_code == 409, wrong.text
    created = await client.post(
        f"/api/v1/purchases/{matching_path}",
        json=payloads[matching_path],
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert created.status_code == 201, created.text
    changed = await client.patch(
        f"/api/v1/products/{product['id']}",
        json={"inventory_type": wrong_path if wrong_path == "item" else "bulk"},
    )
    assert changed.status_code == 409, changed.text
    assert (await client.get(f"/api/v1/products/{product['id']}")).json()[
        "inventory_type"
    ] == inventory_type


async def test_database_rejects_arbitrary_inventory_type(client, test_session_factory):
    product, _, _, _ = await references(client, test_session_factory)
    async with test_session_factory() as db:
        record = await db.get(Product, product["id"])
        record.inventory_type = "arbitrary"
        with pytest.raises(IntegrityError):
            await db.flush()
        await db.rollback()
