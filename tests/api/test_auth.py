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
    from tests.api.test_products import login_admin_user

    return await login_admin_user(client, client.test_session_factory)


async def test_register_returns_created_user(client: AsyncClient):
    payload = user_payload()

    response = await client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == payload["email"]
    assert data["username"] == payload["username"]
    assert data["role"] == payload["role"]
    assert data["is_active"] is True


@pytest.mark.parametrize(
    ("field", "source"),
    [
        ("email", "email"),
        ("username", "username"),
        ("identifier", "email"),
        ("identifier", "username"),
    ],
)
async def test_login_returns_tokens(client: AsyncClient, field: str, source: str):
    payload = await register_user(client)
    value = payload[source]
    if field == "identifier":
        value = f" {value.replace('@example.com', '@EXAMPLE.COM')} "

    response = await client.post(
        "/api/v1/auth/login",
        json={field: value, "password": payload["password"]},
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


async def test_login_prioritizes_the_email_account_for_an_ambiguous_identifier(client: AsyncClient):
    owner = await register_user(client)
    overlapping = user_payload()
    overlapping["username"] = owner["email"]
    overlapping["password"] += uuid4().hex
    assert (await client.post("/api/v1/auth/register", json=overlapping)).status_code == 200

    login = await client.post(
        "/api/v1/auth/login",
        json={"identifier": owner["email"], "password": owner["password"]},
    )
    assert login.status_code == 200
    me = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert me.json()["email"] == owner["email"]

    wrong_account = await client.post(
        "/api/v1/auth/login",
        json={"identifier": owner["email"], "password": overlapping["password"]},
    )
    assert wrong_account.status_code == 401
    assert wrong_account.json() == {"detail": "Invalid username, email or password"}

    explicit_username = await client.post(
        "/api/v1/auth/login",
        json={"username": overlapping["username"], "password": overlapping["password"]},
    )
    assert explicit_username.status_code == 200
    me = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {explicit_username.json()['access_token']}"},
    )
    assert me.json()["email"] == overlapping["email"]


async def test_login_requires_one_identifier_field(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "username": "user", "password": "unused"},
    )
    assert response.status_code == 422


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
    client.headers.pop("Authorization", None)
    response = await client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}


async def test_concurrent_refresh_only_one_succeeds(client):
    import asyncio

    tokens = await login_user(client)
    responses = await asyncio.gather(
        *[
            client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
            for _ in range(2)
        ]
    )
    assert sorted(response.status_code for response in responses) == [200, 401]
