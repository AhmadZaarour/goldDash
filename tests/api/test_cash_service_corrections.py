from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from tests.api.test_backend_access import headers_for
from tests.api.test_cash_outflows import location

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_outflow_corrections_respect_cash_closures_and_original_retry(client):
    location_id = await location(client)
    payload = {
        "location_id": location_id,
        "kind": "expense",
        "amount_usd": "12.50",
        "description": "Cash supplies",
    }
    retry = {"Idempotency-Key": "original-expense"}
    outflow = await client.post("/api/v1/cash/outflows", json=payload, headers=retry)
    assert outflow.status_code == 201
    url = f"/api/v1/cash/outflows/{outflow.json()['id']}"
    correction = {"amount_usd": "15.00", "description": "Packaging"}
    assert (
        await client.patch(url, json=correction, headers={"X-Business-Unit": "factory"})
    ).status_code == 404
    corrected = await client.patch(url, json=correction)
    assert corrected.status_code == 200, corrected.text
    assert Decimal(corrected.json()["amount_usd"]) == Decimal("-15")
    assert corrected.json()["description"] == "Packaging"

    now = datetime.now(UTC)
    snapshot = {
        "idempotency_key": "close-with-expense",
        "location_id": location_id,
        "from_at": (now - timedelta(days=1)).isoformat(),
        "to_at": now.isoformat(),
        "opening_usd": "100",
        "counted_usd": "85",
    }
    close = await client.post("/api/v1/cash/reconciliations", json=snapshot)
    assert close.status_code == 201, close.text
    assert (
        await client.patch(url, json={"amount_usd": "16", "description": "Packaging"})
    ).status_code == 409
    assert (
        await client.patch(url, json={"amount_usd": "15", "description": "Paper supplies"})
    ).status_code == 200
    assert (await client.delete(url)).status_code == 409

    close_url = f"/api/v1/cash/reconciliations/{close.json()['id']}"
    too_large = await client.patch(
        close_url, json={"opening_usd": "0", "counted_usd": "999999999999.99"}
    )
    assert too_large.status_code == 422
    update = await client.patch(close_url, json={"opening_usd": "101", "counted_usd": "85"})
    assert update.status_code == 200, update.text
    assert Decimal(update.json()["expected_usd"]) == 86
    assert Decimal(update.json()["variance_usd"]) == -1
    assert (await client.delete(close_url)).status_code == 204
    assert (await client.post("/api/v1/cash/reconciliations", json=snapshot)).status_code == 409
    history = (
        await client.get("/api/v1/cash/reconciliations", params={"location_id": location_id})
    ).json()
    assert history[0]["voided_at"] is not None
    assert Decimal(history[0]["expected_usd"]) == 86
    assert (await client.delete(url)).status_code == 204
    assert (
        await client.post("/api/v1/cash/outflows", json=payload, headers=retry)
    ).status_code == 409
    cash = await client.get("/api/v1/cash/summary", params={"location_id": location_id})
    assert Decimal(cash.json()["net_usd"]) == 0


async def test_factory_service_payment_corrections_keep_cash_and_job_consistent(
    client, test_session_factory
):
    location_id = await location(client)
    factory = {"X-Business-Unit": "factory"}
    intake_retry = {**factory, "Idempotency-Key": "original-job"}
    intake = {"status": "finished", "notes": "Polish"}
    job = await client.post("/api/v1/servicing", json=intake, headers=intake_retry)
    assert job.status_code == 201
    job_url = f"/api/v1/servicing/{job.json()['id']}"
    original = {"barcode": job.json()["barcode"], "cost": "40", "location_id": location_id}
    payment_retry = {**factory, "Idempotency-Key": "original-payment"}
    payment = await client.post("/api/v1/servicing/sales", json=original, headers=payment_retry)
    assert payment.status_code == 201
    pay_url = f"/api/v1/servicing/sales/{payment.json()['id']}"
    assert (await client.delete(job_url, headers=factory)).status_code == 409
    assert (await client.patch(pay_url, json={"cost": "45"})).status_code == 404
    staff = {**await headers_for(test_session_factory, "employee"), **factory}
    assert (await client.delete(job_url, headers=staff)).status_code == 403
    assert (
        await client.patch(job_url, json={"notes": "Ring polished"}, headers=factory)
    ).status_code == 200

    edited = await client.patch(pay_url, json={"cost": "45"}, headers=factory)
    assert edited.status_code == 200, edited.text
    assert Decimal(edited.json()["amount_usd"]) == Decimal("45")
    params = {"location_id": location_id}
    entries = (await client.get("/api/v1/cash/entries", params=params, headers=factory)).json()
    entry_url = f"/api/v1/cash/outflows/{entries[0]['id']}"
    assert entries[0]["service_sale_id"] == payment.json()["id"]
    assert Decimal(entries[0]["amount_usd"]) == Decimal("45")
    assert (await client.delete(entry_url, headers=factory)).status_code == 409

    outflow = await client.post(
        "/api/v1/cash/outflows",
        json={
            "location_id": location_id,
            "kind": "withdrawal",
            "amount_usd": "30",
            "description": "Removed from drawer",
        },
        headers={**factory, "Idempotency-Key": "factory-outflow"},
    )
    assert outflow.status_code == 201
    assert (await client.delete(pay_url, headers=factory)).status_code == 409
    assert (
        await client.delete(f"/api/v1/cash/outflows/{outflow.json()['id']}", headers=factory)
    ).status_code == 204
    assert (await client.delete(pay_url, headers=factory)).status_code == 204
    cash = await client.get("/api/v1/cash/summary", params=params, headers=factory)
    assert Decimal(cash.json()["net_usd"]) == 0
    record = await client.get(f"/api/v1/servicing/{job.json()['barcode']}", headers=factory)
    assert record.json()["sale"] is None
    assert (
        await client.post("/api/v1/servicing/sales", json=original, headers=payment_retry)
    ).status_code == 409
    assert (await client.delete(job_url, headers=factory)).status_code == 204
    assert (
        await client.post("/api/v1/servicing", json=intake, headers=intake_retry)
    ).status_code == 409
