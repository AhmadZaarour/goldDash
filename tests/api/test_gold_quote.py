import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from redis.exceptions import ConnectionError

from app.services import gold_price
from tests.api.test_backend_access import headers_for

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_shared_cache_coalesces_requests_and_returns_karat_prices(
    client, test_redis, monkeypatch
):
    monkeypatch.setattr(gold_price, "redis", test_redis)
    calls = []

    async def upstream(request):
        calls.append(request)
        await asyncio.sleep(0.02)
        return httpx.Response(
            200, json={"price": 3110, "symbol": "XAU", "updatedAt": "2026-11-03T12:00:00Z"}
        )

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        gold_price.httpx,
        "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(upstream), **kw),
    )
    responses = await asyncio.gather(*[client.get("/api/v1/gold-price") for _ in range(8)])
    # Waiters without a previous quote may receive 503 during the first fetch.
    assert any(r.status_code == 200 for r in responses)
    quote = (await client.get("/api/v1/gold-price")).json()
    assert len(calls) == 1
    assert Decimal(quote["gram_24k_usd"]) == 100
    assert abs(
        Decimal(quote["gram_18k_usd"]) - Decimal(100) * Decimal(".75") / Decimal(".995")
    ) < Decimal("1e-20")
    assert not quote["stale"]
    assert (
        await client.get("/api/v1/gold-price", headers={"Authorization": ""})
    ).status_code == 401


async def test_failure_cooldown_and_stale_fallback(client, test_redis, monkeypatch):
    monkeypatch.setattr(gold_price, "redis", test_redis)
    calls = []

    async def upstream(request):
        calls.append(request)
        return httpx.Response(503)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        gold_price.httpx,
        "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(upstream), **kw),
    )
    for _ in range(3):
        assert (await client.get("/api/v1/gold-price")).status_code == 503
    assert len(calls) == 1
    await test_redis.set(
        gold_price.QUOTE_KEY,
        json.dumps(
            {
                "ounce_usd": "3110",
                "fetched_at": (datetime.now(UTC) - timedelta(minutes=2)).isoformat(),
            }
        ),
    )
    quote = (await client.get("/api/v1/gold-price")).json()
    assert quote["stale"]
    assert quote["ounce_usd"] == "3110"
    assert len(calls) == 1


async def test_cache_failure_never_calls_upstream(client, monkeypatch):
    class FailedRedis:
        async def get(self, key):
            raise ConnectionError("unavailable")

    monkeypatch.setattr(gold_price, "redis", FailedRedis())
    assert (await client.get("/api/v1/gold-price")).status_code == 503


async def test_manual_quote_pauses_workspace_refresh_until_live_is_resumed(
    client, test_redis, test_session_factory, monkeypatch
):
    monkeypatch.setattr(gold_price, "redis", test_redis)
    calls = []

    async def upstream(request):
        calls.append(request)
        return httpx.Response(200, json={"price": 3200})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        gold_price.httpx,
        "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(upstream), **kw),
    )
    quote_url = "/api/v1/gold-price"
    mode_url = f"{quote_url}/quote-mode"
    cashier = await headers_for(test_session_factory, "cashier")
    assert (
        await client.put(mode_url, json={"manual_ounce_usd": "3110"}, headers=cashier)
    ).status_code == 403
    assert (await client.put(mode_url, json={"manual_ounce_usd": "0"})).status_code == 422
    settings = await client.put(mode_url, json={"manual_ounce_usd": "3110"})
    assert settings.status_code == 200, settings.text
    assert Decimal(settings.json()["manual_ounce_usd"]) == 3110
    manual = (await client.get(quote_url)).json()
    assert manual["quote_mode"] == "manual"
    assert not manual["stale"]
    assert Decimal(manual["gram_24k_usd"]) == 100
    assert (await client.get(quote_url)).json() == manual
    assert not calls

    factory = (await client.get(quote_url, headers={"X-Business-Unit": "factory"})).json()
    assert factory["quote_mode"] == "live"
    assert Decimal(factory["ounce_usd"]) == 3200
    assert len(calls) == 1
    assert (await client.get(quote_url)).json() == manual

    resumed = await client.put(mode_url, json={"manual_ounce_usd": None})
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["manual_ounce_usd"] is None
    live = (await client.get(quote_url)).json()
    assert live["quote_mode"] == "live"
    assert Decimal(live["ounce_usd"]) == 3200
