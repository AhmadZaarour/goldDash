"""Public PATCH operations preserve omitted fields and reject invalid supplied values."""

from decimal import Decimal

import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_category_names_are_trimmed_and_partial_updates_preserve_name(client):
    created = await client.post(
        "/api/v1/categories", json={"name": "  Rings  ", "description": "Original"}
    )
    assert created.status_code == 201
    assert created.json()["name"] == "Rings"
    url = f"/api/v1/categories/{created.json()['id']}"
    updated = await client.patch(url, json={"description": None})
    assert updated.status_code == 200
    assert updated.json()["name"] == "Rings"
    assert updated.json()["description"] is None
    for value in [None, "", "   ", "x" * 51]:
        assert (await client.patch(url, json={"name": value})).status_code == 422
    assert (await client.get(url)).json() == updated.json()


async def test_gold_purity_partial_updates_and_input_bounds(client):
    created = await client.post(
        "/api/v1/goldpurities", json={"name": " Fine ", "karat": 24, "purity": 99.9}
    )
    assert created.status_code == 201
    assert created.json()["name"] == "Fine"
    url = f"/api/v1/goldpurities/{created.json()['id']}"
    updated = await client.patch(url, json={"name": "  Fine gold  "})
    assert updated.status_code == 200
    assert updated.json()["name"] == "Fine gold"
    assert updated.json()["karat"] == 24
    assert updated.json()["purity"] == 99.9
    for invalid in [
        {"name": None},
        {"name": "x" * 51},
        {"name": "   "},
        {"karat": None},
        {"karat": 0},
        {"karat": 25},
        {"purity": None},
        {"purity": 0},
        {"purity": 100.1},
        {"purity": "NaN"},
        {"purity": "Infinity"},
    ]:
        assert (await client.patch(url, json=invalid)).status_code == 422
    assert (await client.get(url)).json() == updated.json()
    valid_boundary = await client.post(
        "/api/v1/goldpurities", json={"name": "One karat", "karat": 1, "purity": 100}
    )
    assert valid_boundary.status_code == 201


@pytest.mark.parametrize(
    "change", [{"name": "x" * 51}, {"name": "   "}, {"karat": 25}, {"purity": "NaN"}]
)
async def test_gold_purity_creation_rejects_invalid_fields(client, change):
    payload = {"name": "Fine", "karat": 24, "purity": 99.9, **change}
    assert (await client.post("/api/v1/goldpurities", json=payload)).status_code == 422


async def test_servicing_partial_updates_preserve_cost_and_status(client):
    customer = await client.post("/api/v1/customers", json={"name": "Service customer"})
    assert customer.status_code == 201
    created = await client.post(
        "/api/v1/servicing",
        json={
            "customer_id": customer.json()["id"],
            "barcode": "REPAIR-VALIDATION",
            "cost": "12.50",
            "notes": "Needs polishing",
        },
    )
    assert created.status_code == 201
    url = f"/api/v1/servicing/{created.json()['id']}"
    updated = await client.patch(url, json={"status": " completed "})
    assert updated.status_code == 200
    assert updated.json()["status"] == "completed"
    assert Decimal(updated.json()["cost"]) == Decimal("12.50")
    notes_only = await client.patch(url, json={"notes": None})
    assert notes_only.status_code == 200
    assert notes_only.json()["notes"] is None
    assert notes_only.json()["status"] == "completed"
    assert Decimal(notes_only.json()["cost"]) == Decimal("12.50")
    for invalid in [
        {"cost": None},
        {"status": None},
        {"status": "   "},
        {"cost": "-0.01"},
        {"cost": "1.234"},
        {"cost": "1000000000000.00"},
    ]:
        assert (await client.patch(url, json=invalid)).status_code == 422
    assert (await client.get("/api/v1/servicing/REPAIR-VALIDATION")).json() == notes_only.json()


@pytest.mark.parametrize("cost", ["-0.01", "1.234", "1000000000000.00"])
async def test_service_creation_rejects_invalid_usd_values(client, cost):
    customer = await client.post("/api/v1/customers", json={"name": "Service customer"})
    payload = {"customer_id": customer.json()["id"], "barcode": "INVALID-COST", "cost": cost}
    assert (await client.post("/api/v1/servicing", json=payload)).status_code == 422
