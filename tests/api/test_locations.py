from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.schemas.auth import TokenResponse

from tests.api.test_auth import (
    login_user,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")

def locations_payload() -> dict[str,str]:
    suffix = uuid4().hex
    return {
        "name": f"name-{suffix}",
        "code": f"code-{suffix}",
        "address": f"address-{suffix}",
        "is_active": True,
    }

async def test_create_location(client: AsyncClient):
    login_response = await login_user(client)
    access_token = login_response["access_token"]

    payload = locations_payload()
    response = await client.post(
        "api/v1/locations",
        json=payload,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == payload["name"]
    assert data["code"] == payload["code"]
    assert data["address"] == payload["address"]
    assert data["is_active"] == payload["is_active"]
    return response