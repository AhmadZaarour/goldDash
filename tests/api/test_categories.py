from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.schemas.auth import TokenResponse

from tests.api.test_auth import (
    login_user,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")

def category_payload() -> dict[str, str]:
    suffix = uuid4().hex
    return {
        "name": f"category-{suffix}",
        "description": f"description-{suffix}",
    }

async def test_create_category(client: AsyncClient):
    login_response = await login_user(client)
    access_token = login_response["access_token"]

    category_payload_data = category_payload()

    response = await client.post(
        "/api/v1/categories",
        json=category_payload_data,
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == category_payload_data["name"]
    assert data["description"] == category_payload_data["description"]