from uuid import uuid4

import pytest

from app.core.security import create_access_token, hash_password
from app.models import User

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def headers_for(test_session_factory, role):
    async with test_session_factory() as db:
        user = User(
            email=f"{uuid4().hex}@example.com",
            username=uuid4().hex,
            role=role,
            password_hash=hash_password("RoleTestPassword123!"),
        )
        db.add(user)
        await db.commit()
        return {"Authorization": f"Bearer {create_access_token(str(user.id))}"}


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/products",
        "/api/v1/categories",
        "/api/v1/customers",
        "/api/v1/suppliers",
        "/api/v1/locations",
        "/api/v1/goldpurities",
        "/api/v1/purchases",
        "/api/v1/sales",
        "/api/v1/inventory/items",
        "/api/v1/balance",
    ],
)
async def test_business_reads_require_authentication(client, path):
    assert (await client.get(path, headers={"Authorization": ""})).status_code == 401


@pytest.mark.parametrize("role", ["employee", "cashier"])
async def test_only_admin_can_purchase_settle_and_register(client, test_session_factory, role):
    headers = await headers_for(test_session_factory, role)
    for path in [
        "/api/v1/purchases/item",
        "/api/v1/purchases/stock",
        "/api/v1/sales/stock",
        "/api/v1/suppliers/1/settlements",
        "/api/v1/auth/register",
    ]:
        response = await client.post(path, json={}, headers=headers)
        assert response.status_code == 403, (path, response.text)
    assert (
        await client.post("/api/v1/categories", json={"name": "Unauthorized"}, headers=headers)
    ).status_code == 403


async def test_employee_cannot_sell_and_cashier_cannot_transfer(client, test_session_factory):
    employee = await headers_for(test_session_factory, "employee")
    cashier = await headers_for(test_session_factory, "cashier")
    assert (await client.post("/api/v1/sales/item", json={}, headers=employee)).status_code == 403
    assert (
        await client.post("/api/v1/inventory/returns", json={}, headers=employee)
    ).status_code == 403
    assert (
        await client.post("/api/v1/inventory/stocks/transfer", json={}, headers=cashier)
    ).status_code == 403
    assert (await client.get("/api/v1/categories", headers=employee)).status_code == 200
    assert (await client.get("/api/v1/inventory/items", headers=cashier)).status_code == 200


async def test_registration_is_not_public_and_inactive_users_cannot_login(
    client, test_session_factory
):
    from tests.api.test_auth import user_payload

    payload = user_payload()
    assert (
        await client.post("/api/v1/auth/register", json=payload, headers={"Authorization": ""})
    ).status_code == 401
    created = await client.post("/api/v1/auth/register", json=payload)
    assert created.status_code == 200
    async with test_session_factory() as db:
        user = await db.get(User, created.json()["id"])
        user.is_active = False
        await db.commit()
    response = await client.post(
        "/api/v1/auth/login", json={"email": payload["email"], "password": payload["password"]}
    )
    assert response.status_code == 401
