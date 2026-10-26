from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import hash_password, verify_password
from app.models.user import User

pytestmark = pytest.mark.asyncio(loop_scope="session")

def admin_payload() -> dict[str, str]:
    suffix = uuid4().hex
    return {
        "email": f"admin-{suffix}@example.com",
        "username": f"admin-{suffix}",
        "password": "TestPassword123!",
        "role": "admin",
    }

async def create_test_admin(
    admin_data: dict[str, str],
    session_factory: async_sessionmaker[AsyncSession],
) -> User:
    async with session_factory() as db:
        admin = User(
            email=admin_data["email"],
            username=admin_data["username"],
            password_hash=hash_password(admin_data["password"]),
            role=admin_data["role"],
        )
        db.add(admin)
        await db.commit()
        await db.refresh(admin)
        return admin

async def login_admin_user(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
) -> dict[str, str]:
    payload = admin_payload()
    await create_test_admin(payload, session_factory)
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": payload["email"],
            "password": payload["password"],
        },
    )
    assert response.status_code == 200
    return response.json()


async def test_create_admin(test_session_factory: async_sessionmaker[AsyncSession]):
    payload = admin_payload()

    admin = await create_test_admin(payload, test_session_factory)

    assert admin.email == payload["email"]
    assert admin.username == payload["username"]
    assert admin.role == "admin"
    assert verify_password(payload["password"], admin.password_hash)

def gold_purity_payload() -> dict[str, str]:
    suffix = uuid4().hex
    return {
        "name": f"gold-purity-{suffix}",
        "karat": 24,
        "purity": 99.9,
    }

def category_payload() -> dict[str, str]:
    suffix = uuid4().hex
    return {
        "name": f"category-{suffix}",
        "description": f"description-{suffix}",
    }
def product_payload(p_id: int, c_id: int) -> dict[str, str]:
    suffix = uuid4().hex
    return {
        "sku": f"sku-{suffix}",
        "name": f"product-{suffix}",
        "description": f"description-{suffix}",
        "category_id": c_id,
        "purity_id": p_id,
        "inventory_type": "type",
    }

async def test_create_product(
    client: AsyncClient,
    test_session_factory: async_sessionmaker[AsyncSession],
):
    # Register and login a user to get an access token
    login_response = await login_admin_user(client, test_session_factory)
    access_token = login_response["access_token"]

    # Add category and gold purity to the database
    category_payload_data = category_payload()
    gold_purity_payload_data = gold_purity_payload()

    response_category = await client.post(
        "/api/v1/categories",
        json=category_payload_data,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response_category.status_code == 201

    response_gold_purity = await client.post(
        "/api/v1/goldpurities",
        json=gold_purity_payload_data,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response_gold_purity.status_code == 201

    # Create a product payload
    payload = product_payload(response_gold_purity.json()["id"], response_category.json()["id"])

    # Make a request to create a product
    response = await client.post(
        "/api/v1/products",
        json=payload,
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["sku"] == payload["sku"]
    assert data["name"] == payload["name"]
    assert data["description"] == payload["description"]
    assert data["category_id"] == payload["category_id"]
    assert data["purity_id"] == payload["purity_id"]
    assert data["inventory_type"] == payload["inventory_type"]
    return response