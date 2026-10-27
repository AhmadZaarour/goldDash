from uuid import uuid4

import pytest
from httpx import AsyncClient

from tests.api.test_auth import (
    login_user,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


def supplier_payload() -> dict[str, str]:
    suffix = uuid4().hex
    return {
        "name": f"name-{suffix}",
        "phone": str(int(suffix[:12], 16)),
        "is_active": True,
    }


async def test_create_supplier(client: AsyncClient):

    login_response = await login_user(client)
    access_token = login_response["access_token"]

    payload = supplier_payload()
    response = await client.post(
        "/api/v1/suppliers",
        json=payload,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == payload["name"]
    assert data["phone"] == payload["phone"]
    assert data["is_active"] == payload["is_active"]
    return response
