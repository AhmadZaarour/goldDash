import re

import pytest
from sqlalchemy import select

from app.models import Purchase, PurchaseItem
from tests.api.test_auth import login_user
from tests.api.test_purchase import test_create_purchase as create_purchase

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_purchase_generates_unique_item_barcodes(client, test_session_factory):
    response, _, inventory = await create_purchase(client, test_session_factory)
    first = inventory.json()
    assert re.fullmatch(r"GI[0-9A-F]{16}", first["barcode"])
    tokens = await login_user(client)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    async with test_session_factory() as db:
        purchase = await db.get(Purchase, response.json()["id"])
        line = await db.scalar(select(PurchaseItem).where(PurchaseItem.purchase_id == purchase.id))
        payload = {
            "supplier_id": purchase.supplier_id,
            "created_by": purchase.created_by,
            "location_id": purchase.location_id,
            "items": [
                {
                    "supplier_id": purchase.supplier_id,
                    "product_id": line.product_id,
                    "weight": "1",
                    "gold_price_per_gram": "100",
                    "gold_charge_in_grams": "1",
                    "making_charge": "5",
                    "barcode": first["barcode"],
                }
            ],
        }
    # Legacy input cannot override or reuse a saved barcode.
    response = await client.post("/api/v1/purchases/item", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    items = (await client.get("/api/v1/inventory/items")).json()
    assert len(items) == 2
    codes = [item["barcode"] for item in items]
    assert len(set(codes)) == 2
    assert all(re.fullmatch(r"GI[0-9A-F]{16}", code) for code in codes)
    assert (await client.get(f"/api/v1/inventory/items/{first['id']}")).json()["barcode"] == first[
        "barcode"
    ]
