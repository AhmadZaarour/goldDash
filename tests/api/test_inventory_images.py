import pytest
from sqlalchemy import select

from app.models import InventoryItem, InventoryStock, Purchase, PurchaseItem
from tests.api.test_auth import login_user
from tests.api.test_purchase import test_create_purchase as create_purchase

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_item_image_creation_update_and_clear(client, test_session_factory):
    purchase, _, inventory = await create_purchase(client, test_session_factory)
    assert inventory.json()["image_url"] is None
    tokens = await login_user(client)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    async with test_session_factory() as db:
        invoice = await db.get(Purchase, purchase.json()["id"])
        line = await db.scalar(select(PurchaseItem).where(PurchaseItem.purchase_id == invoice.id))
        payload = {
            "supplier_id": invoice.supplier_id,
            "created_by": invoice.created_by,
            "location_id": invoice.location_id,
            "items": [
                {
                    "supplier_id": invoice.supplier_id,
                    "product_id": line.product_id,
                    "weight": 1,
                    "gold_price_per_gram": 100,
                    "gold_charge_in_grams": 1,
                    "making_charge": 5,
                    "barcode": "WITH-IMAGE",
                    "image_url": "https://example.com/ring.jpg",
                }
            ],
        }
    response = await client.post("/api/v1/purchases/item", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    items = (await client.get("/api/v1/inventory/items")).json()
    purchase_items = (await client.get(f"/api/v1/purchases/items/{response.json()['id']}")).json()
    item = next(row for row in items if row["purchase_item_id"] == purchase_items[0]["id"])
    assert item["image_url"] == "https://example.com/ring.jpg"
    url = f"/api/v1/inventory/items/{item['id']}/image"
    updated = await client.patch(
        url, json={"image_url": "https://example.com/new.jpg"}, headers=headers
    )
    assert updated.status_code == 200
    assert updated.json()["image_url"] == "https://example.com/new.jpg"
    assert updated.json()["barcode"] == item["barcode"]
    detail_url = f"/api/v1/inventory/items/{item['id']}"
    assert (await client.get(detail_url)).json() == updated.json()
    async with test_session_factory() as db:
        assert (await db.get(InventoryItem, item["id"])).image_url == "https://example.com/new.jpg"
    cleared = await client.patch(url, json={"image_url": None}, headers=headers)
    assert cleared.status_code == 200
    assert (await client.get(detail_url)).json()["image_url"] is None
    assert (
        await client.patch(url, json={"image_url": "not-a-url"}, headers=headers)
    ).status_code == 422
    assert (await client.patch(url, json={}, headers=headers)).status_code == 422
    assert (
        await client.patch(url, json={"image_url": None}, headers={"Authorization": ""})
    ).status_code == 401
    missing = await client.patch(
        "/api/v1/inventory/items/2147483647/image", json={"image_url": None}, headers=headers
    )
    assert missing.status_code == 404
    assert "image_url" not in InventoryStock.__table__.columns
