from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.api.test_auth import (
    login_user,
)
from tests.api.test_locations import test_create_location
from tests.api.test_products import test_create_product
from tests.api.test_purchase import test_create_purchase, test_create_purchase_stock
from tests.api.test_suppliers import test_create_supplier

pytestmark = pytest.mark.asyncio(loop_scope="session")


def sale_item_payload(inv_id) -> dict[str, str]:
    return {
        "inventory_item_id": inv_id,
        "gold_price_per_gram": 100.5,
        "discount": 2.5,
        "sell_price": 200.9,
    }


def sale_payload(created_by: int, l_id: int, inv_id: int) -> dict[str, str]:
    suffix = uuid4().hex
    return {
        "invoice_number": f"invoice_number-{suffix}",
        "notes": f"notes-{suffix}",
        "created_by": created_by,
        "location_id": l_id,
        "items": [sale_item_payload(inv_id)],
    }


def sale_stock_item_payload(s_id, gp_id) -> dict[str, str]:
    return {
        "supplier_id": s_id,
        "gold_purity_id": gp_id,
        "weight": 1.6,
        "gold_charge_in_grams": 1.6,
        "making_charge": 3.5,
    }


def sale_stock_payload(created_by, l_id, s_id, gp_id):
    suffix = uuid4().hex
    return {
        "invoice_number": f"invoice_number-{suffix}",
        "notes": f"notes-{suffix}",
        "created_by": created_by,
        "location_id": l_id,
        "item": sale_stock_item_payload(s_id, gp_id),
    }


async def test_create_sale(
    client: AsyncClient, test_session_factory: async_sessionmaker[AsyncSession]
):
    login_response = await login_user(client)
    access_token = login_response["access_token"]
    user_response = await client.get(
        "api/v1/users/me", headers={"Authorization": f"Bearer {access_token}"}
    )
    purchase_response, items_response, inv_response = await test_create_purchase(
        client, test_session_factory
    )
    payload = sale_payload(
        user_response.json()["id"],
        purchase_response.json()["location_id"],
        inv_response.json()["id"],
    )

    response = await client.post(
        "api/v1/sales/item",
        json=payload,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["invoice_number"] == payload["invoice_number"]
    assert data["notes"] == payload["notes"]


async def test_create_sale_stock(
    client: AsyncClient, test_session_factory: async_sessionmaker[AsyncSession]
):
    login_response = await login_user(client)
    access_token = login_response["access_token"]
    user_response = await client.get(
        "api/v1/users/me", headers={"Authorization": f"Bearer {access_token}"}
    )
    location_response = await test_create_location(client)
    supplire_response = await test_create_supplier(client)
    product_response = await test_create_product(
        client, test_session_factory, inventory_type="bulk"
    )
    await test_create_purchase_stock(
        client,
        test_session_factory,
        product_id=product_response.json()["id"],
        location_id=location_response.json()["id"],
    )
    b_response = await client.get(
        "api/v1/balance",
    )
    assert b_response.status_code == 200
    balances = b_response.json()
    assert any(
        balance["purity_id"] == product_response.json()["purity_id"]
        and balance["location_id"] == location_response.json()["id"]
        and balance["placement"] == "factory"
        for balance in balances
    )
    payload = sale_stock_payload(
        user_response.json()["id"],
        location_response.json()["id"],
        supplire_response.json()["id"],
        product_response.json()["purity_id"],
    )

    response = await client.post(
        "api/v1/sales/stock",
        json=payload,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["invoice_number"] == payload["invoice_number"]
    assert data["notes"] == payload["notes"]
