import pytest
from httpx import ASGITransport, AsyncClient
from redis.exceptions import RedisError

from app.core.config import settings
from app.main import create_app

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_cors_allows_only_configured_origins_and_exposes_pagination():
    application = create_app(
        settings.model_copy(update={"cors_origins": ["http://localhost:5173"]})
    )
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        allowed = await client.options(
            "/api/v1/inventory/items",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )
        assert allowed.status_code == 200
        assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
        blocked = await client.options(
            "/api/v1/inventory/items",
            headers={
                "Origin": "https://unconfigured.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert blocked.status_code == 400
        assert "access-control-allow-origin" not in blocked.headers
        health = await client.get("/health", headers={"Origin": "http://localhost:5173"})
        assert health.json() == {"status": "ok"}
        assert "X-Total-Count" in health.headers["access-control-expose-headers"]


async def test_readiness_detects_redis_failure(client, monkeypatch):
    import app.main

    async def unavailable():
        raise RedisError("internal details must not be exposed")

    monkeypatch.setattr(app.main.redis, "ping", unavailable)
    response = await client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {"detail": "A required service is unavailable"}


async def test_openapi_operation_ids_are_unique_and_retired_books_deprecated(client):
    schema = (await client.get("/openapi.json")).json()
    ids = []
    for path, operations in schema["paths"].items():
        for operation in operations.values():
            if isinstance(operation, dict) and "operationId" in operation:
                ids.append(operation["operationId"])
                if "Book" in path:
                    assert operation["deprecated"] is True
    assert len(ids) == len(set(ids))
