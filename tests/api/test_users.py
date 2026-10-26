from uuid import uuid4
from app.schemas.auth import TokenResponse
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio(loop_scope="session")


def user_payload() -> dict[str, str]:
    suffix = uuid4().hex
    return {
        "email": f"user-{suffix}@example.com",
        "username": f"user-{suffix}",
        "password": "TestPassword123!",
        "role": "employee",
    }

async def register_user(client: AsyncClient) -> dict[str, str]:
    payload = user_payload()
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 200
    return payload

async def get_user(client: AsyncClient) -> dict[str, str]:
    payload = register_user(client)
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": payload["email"],
            "password": payload["password"],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == TokenResponse.model_fields["token_type"].default
    assert data["access_token"]
    assert data["refresh_token"]

    user_response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {data['access_token']}"}
    )

    assert user_response.status_code == 200