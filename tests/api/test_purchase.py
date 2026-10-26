from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.schemas.auth import TokenResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.api.test_auth import (
    login_user,
)
from tests.api.test_products import test_create_product
from tests.api.test_suppliers import test_create_supplier
from tests.api.test_locations import test_create_location

pytestmark = pytest.mark.asyncio(loop_scope="session")

def items_payload(s_id, p_id) -> dict[str,str]:
    return{
        "supplier_id": s_id,
        "product_id": p_id,
        "weight": 2.1,
        "gold_price_per_gram": 100.5,
        "gold_charge_in_grams": 201.5,
        "making_charge": 8.6,
        "barcode": "52552556",
    }
def purchase_payload(created_by: int, location_id: int, s_id: int, p_id: int) -> dict[str,str]:
    suffix = uuid4().hex
    return{
        "invoice_number": f"invoice_number-{suffix}",
        "notes": f"notes-{suffix}",
        "created_by": created_by,
        "location_id": location_id,
        "items": [items_payload(s_id, p_id)],
    }

def purchase_stock_item_payload(p_id) -> dict[str,str]:
    return {
        "product_id": p_id,
        "stock_for": "factory",
        "weight": 2.6,
        "cost_per_gram": 55.05,
    }

def purchase_stock_payload(created_by, location_id, s_id, p_id) -> dict[str,str]:
    suffix = uuid4().hex
    return{
        "invoice_number": f"invoice_number-{suffix}",
        "notes": f"notes-{suffix}",
        "created_by": created_by,
        "location_id": location_id,
        "item": purchase_stock_item_payload(p_id),
    }

async def test_create_purchase(client: AsyncClient, test_session_factory: async_sessionmaker[AsyncSession]):

    login_response = await login_user(client)
    access_token = login_response["access_token"]
    user_response = await client.get(
        "api/v1/users/me",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    location_response = await test_create_location(client)
    supplire_response = await test_create_supplier(client)
    product_response = await test_create_product(client, test_session_factory)

    payload = purchase_payload(user_response.json()["id"],location_response.json()["id"],
                               supplire_response.json()["id"], product_response.json()["id"])

    response = await client.post(
        "api/v1/purchases/item",
        json=payload,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    items_response = await client.get(
        f"api/v1/purchases/items/{response.json()["id"]}"
    )
    inv_response = await client.get(
        f"api/v1/inventory/{items_response.json()[0]["id"]}"
    )
    assert response.status_code == 201
    data = response.json()
    assert data["invoice_number"] == payload["invoice_number"]
    assert data["notes"] == payload["notes"]
    assert data["created_by"] == payload["created_by"]
    assert data["location_id"] == payload["location_id"]
    return response, items_response, inv_response

async def test_create_purchase_stock(
    client: AsyncClient,
    test_session_factory: async_sessionmaker[AsyncSession],
    product_id: int | None = None,
    location_id: int | None = None,
):
    login_response = await login_user(client)
    access_token = login_response["access_token"]
    user_response = await client.get(
        "api/v1/users/me",
        headers={"Authorization": f"Bearer {access_token}"}
        )
    if product_id is None:
        product_response = await test_create_product(client, test_session_factory)
        product_id = product_response.json()["id"]
    if location_id is None:
        location_response = await test_create_location(client)
        location_id = location_response.json()["id"]

    payload = purchase_stock_payload(
        user_response.json()["id"], location_id, 1, product_id
    )
    print(payload)
    response = await client.post(
        "api/v1/purchases/stock",
        json=payload,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["invoice_number"] == payload["invoice_number"]
    assert data["notes"] == payload["notes"]
    return response
