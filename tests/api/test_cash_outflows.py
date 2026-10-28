import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from tests.api.test_backend_access import headers_for

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def location(client):
    response = await client.post("/api/v1/locations", json={"name": "Cash drawer", "code": "CASH"})
    assert response.status_code == 201
    return response.json()["id"]


async def test_expenses_withdrawals_retries_and_reconciliation(client):
    location_id = await location(client)
    payload = {
        "location_id": location_id,
        "kind": "expense",
        "amount_usd": "12.50",
        "description": "Packaging supplies",
        "category": "Supplies",
    }
    headers = {"Idempotency-Key": "expense-1"}
    results = await asyncio.gather(
        *[client.post("/api/v1/cash/outflows", json=payload, headers=headers) for _ in range(2)]
    )
    assert [r.status_code for r in results] == [201, 201]
    assert results[0].json() == results[1].json()
    assert Decimal(results[0].json()["amount_usd"]) == Decimal("-12.50")
    assert results[0].json()["description"] == "Packaging supplies"
    changed = {**payload, "amount_usd": "13.00"}
    assert (
        await client.post("/api/v1/cash/outflows", json=changed, headers=headers)
    ).status_code == 409
    withdrawal = await client.post(
        "/api/v1/cash/outflows",
        json={
            "location_id": location_id,
            "kind": "withdrawal",
            "amount_usd": "20",
            "description": "Owner cash removal",
        },
        headers={"Idempotency-Key": "withdrawal-1"},
    )
    assert withdrawal.status_code == 201
    summary = (await client.get("/api/v1/cash/summary", params={"location_id": location_id})).json()
    assert Decimal(summary["expenses_usd"]) == Decimal("12.50")
    assert Decimal(summary["withdrawals_usd"]) == 20
    assert Decimal(summary["net_usd"]) == Decimal("-32.50")
    history = await client.get(
        "/api/v1/cash/entries", params={"location_id": location_id, "kind": "expense"}
    )
    assert history.headers["X-Total-Count"] == "1"
    assert history.json() == [results[0].json()]
    now = datetime.now(UTC)
    closed = await client.post(
        "/api/v1/cash/reconciliations",
        json={
            "idempotency_key": "close-outflows",
            "location_id": location_id,
            "from_at": (now - timedelta(days=1)).isoformat(),
            "to_at": now.isoformat(),
            "opening_usd": "100",
            "counted_usd": "67.50",
        },
    )
    assert closed.status_code == 201
    assert Decimal(closed.json()["expected_usd"]) == Decimal("67.50")
    assert Decimal(closed.json()["variance_usd"]) == 0


@pytest.mark.parametrize(
    "patch",
    [
        {"amount_usd": "0"},
        {"amount_usd": "-1"},
        {"amount_usd": "1.001"},
        {"description": "   "},
        {"kind": "bank_deposit"},
    ],
)
async def test_invalid_outflows_rejected(client, patch):
    payload = {
        "location_id": 1,
        "kind": "expense",
        "amount_usd": "10",
        "description": "Supplies",
        **patch,
    }
    response = await client.post(
        "/api/v1/cash/outflows", json=payload, headers={"Idempotency-Key": "invalid"}
    )
    assert response.status_code == 422


async def test_outflow_permissions_and_inactive_drawer(client, test_session_factory):
    location_id = await location(client)
    data = {
        "location_id": location_id,
        "kind": "withdrawal",
        "amount_usd": "10",
        "description": "Removal",
    }
    for role in ["cashier", "employee"]:
        headers = await headers_for(test_session_factory, role)
        headers["Idempotency-Key"] = "forbidden"
        assert (
            await client.post("/api/v1/cash/outflows", json=data, headers=headers)
        ).status_code == 403
    assert (await client.post("/api/v1/cash/outflows", json=data)).status_code == 422
    assert (
        await client.patch(f"/api/v1/locations/{location_id}", json={"is_active": False})
    ).status_code == 200
    rejected = await client.post(
        "/api/v1/cash/outflows", json=data, headers={"Idempotency-Key": "inactive"}
    )
    assert rejected.status_code == 409
    assert (
        await client.get("/api/v1/cash/entries", params={"location_id": location_id})
    ).json() == []
