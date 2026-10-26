from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.schemas.auth import TokenResponse

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


async def login_user(client: AsyncClient) -> dict[str, str]:
    payload = await register_user(client)
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": payload["email"],
            "password": payload["password"],
        },
    )
    assert response.status_code == 200
    return response.json()


async def test_register_returns_created_user(client: AsyncClient):
    payload = user_payload()

    response = await client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == payload["email"]
    assert data["username"] == payload["username"]
    assert data["role"] == payload["role"]
    assert data["is_active"] is True


async def test_login_returns_tokens(client: AsyncClient):
    payload = await register_user(client)

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == TokenResponse.model_fields["token_type"].default
    assert data["access_token"]
    assert data["refresh_token"]


async def test_login_rejects_invalid_password(client: AsyncClient):
    payload = await register_user(client)

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password"}
    assert response.headers["www-authenticate"] == "Bearer"


async def test_refresh_rotates_token(client: AsyncClient):
    tokens = await login_user(client)

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )

    assert response.status_code == 200
    new_tokens = response.json()
    assert new_tokens["access_token"]
    assert new_tokens["refresh_token"] != tokens["refresh_token"]

    old_token_response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert old_token_response.status_code == 401


async def test_logout_revokes_refresh_token(client: AsyncClient):
    tokens = await login_user(client)

    response = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Successfully logged out"}

    refresh_response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refresh_response.status_code == 401


async def test_me_returns_authenticated_user(client: AsyncClient):
    payload = await register_user(client)
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    client.headers["Authorization"] = f"Bearer {login_response.json()['access_token']}"

    response = await client.get("/api/v1/auth/me")

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == payload["email"]
    assert data["username"] == payload["username"]
    assert data["role"] == "employee"


async def test_me_requires_authentication(client: AsyncClient):
    response = await client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}
