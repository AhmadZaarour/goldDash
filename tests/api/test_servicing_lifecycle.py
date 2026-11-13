import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.models import CashEntry, InventoryService, ServiceSale
from tests.api.test_backend_access import headers_for

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def create(client, *, status="in_progress", headers=None):
    response = await client.post(
        "/api/v1/servicing",
        json={"status": status},
        headers={
            "Idempotency-Key": uuid4().hex,
            **(headers or {}),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def location(client):
    response = await client.post("/api/v1/locations", json={"name": "Shop", "code": "SRV"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def test_service_intake_generated_barcodes_and_retry(client):
    headers = {"Idempotency-Key": "intake"}
    response = await client.post("/api/v1/servicing", json={}, headers=headers)
    assert response.status_code == 201, response.text
    record = response.json()
    assert record["barcode"].startswith("SV")
    assert record["status"] == "in_progress"
    assert record["notes"] is None and record["customer_id"] is None
    assert record["sale"] is None
    assert (await client.post("/api/v1/servicing", json={}, headers=headers)).json() == record
    assert (
        await client.post("/api/v1/servicing", json={"notes": "different"}, headers=headers)
    ).status_code == 409
    another = await create(client)
    assert another["barcode"] != record["barcode"]
    assert (await client.get(f"/api/v1/servicing/{record['barcode']}")).json() == record
    assert (await client.post("/api/v1/servicing", json={})).status_code == 422


async def test_service_checkout_cash_profit_and_double_payment_guard(client, test_session_factory):
    loc = await location(client)
    service = await create(client)
    data = {"barcode": service["barcode"], "location_id": loc, "cost": "12.50"}
    headers = {"Idempotency-Key": "checkout"}
    assert (
        await client.post("/api/v1/servicing/sales", json=data, headers=headers)
    ).status_code == 409
    assert (
        await client.patch(
            f"/api/v1/servicing/{service['id']}", json={"status": "finished", "notes": "Polished"}
        )
    ).status_code == 200
    sale = await client.post("/api/v1/servicing/sales", json=data, headers=headers)
    assert sale.status_code == 201, sale.text
    paid = sale.json()
    assert paid["notes"] == "Polished" and paid["unit"] == "showroom"
    assert Decimal(paid["amount_usd"]) == Decimal("12.50")
    assert (await client.post("/api/v1/servicing/sales", json=data, headers=headers)).json() == paid
    assert (
        await client.post(
            "/api/v1/servicing/sales", json=data, headers={"Idempotency-Key": "other"}
        )
    ).status_code == 409
    assert (
        await client.patch(f"/api/v1/servicing/{service['id']}", json={"status": "in_progress"})
    ).status_code == 409
    record = (await client.get("/api/v1/servicing", params={"barcode": service["barcode"]})).json()[
        0
    ]
    assert record["sale"] == paid
    assert (await client.get("/api/v1/servicing/sales")).json() == [paid]
    summary = (await client.get("/api/v1/cash/summary", params={"location_id": loc})).json()
    assert Decimal(summary["service_received_usd"]) == Decimal("12.50")
    assert Decimal(summary["net_usd"]) == Decimal("12.50")
    entries = (
        await client.get(
            "/api/v1/cash/entries", params={"location_id": loc, "kind": "service_sale"}
        )
    ).json()
    assert len(entries) == 1 and entries[0]["service_sale_id"] == paid["id"]
    month = datetime.now(UTC).strftime("%Y-%m")
    for path in ["/api/v1/operations/profit", "/api/v1/insights/monthly-profit"]:
        report = await client.get(path, params={"month": month, "location_id": loc})
        assert report.status_code == 200, report.text
        assert Decimal(report.json()["service_sales_usd"]) == Decimal("12.50")
        assert report.json()["service_sales_count"] == 1
        key = "profit_usd" if "operations" in path else "net_profit_usd"
        assert Decimal(report.json()[key]) == Decimal("12.50")
    company = await client.get(
        "/api/v1/operations/profit", params={"month": month, "company": True}
    )
    assert Decimal(company.json()["service_sales_usd"]) == Decimal("12.50")
    async with test_session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(ServiceSale)) == 1
        assert await db.scalar(select(func.count()).select_from(CashEntry)) == 1


async def test_service_checkout_scope_roles_and_inactive_location(client, test_session_factory):
    loc = await location(client)
    employee = await headers_for(test_session_factory, "employee")
    cashier = await headers_for(test_session_factory, "cashier")
    service = await create(client, status="finished", headers=employee)
    data = {"barcode": service["barcode"], "location_id": loc, "cost": "0"}
    key = {"Idempotency-Key": uuid4().hex}
    assert (await client.get("/api/v1/servicing", headers=cashier)).status_code == 200
    assert (
        await client.post("/api/v1/servicing", json={}, headers={**cashier, **key})
    ).status_code == 403
    assert (
        await client.patch(
            f"/api/v1/servicing/{service['id']}", json={"status": "in_progress"}, headers=cashier
        )
    ).status_code == 403
    assert (
        await client.post("/api/v1/servicing/sales", json=data, headers={**employee, **key})
    ).status_code == 403
    assert (
        await client.get(
            "/api/v1/servicing",
            params={"barcode": service["barcode"]},
            headers={"X-Business-Unit": "factory"},
        )
    ).json() == []
    assert (
        await client.post(
            "/api/v1/servicing/sales", json=data, headers={**key, "X-Business-Unit": "factory"}
        )
    ).status_code == 404
    assert (
        await client.post(
            "/api/v1/servicing/sales", json={**data, "location_id": 999999}, headers=key
        )
    ).status_code == 409
    await client.patch(f"/api/v1/locations/{loc}", json={"is_active": False})
    assert (await client.post("/api/v1/servicing/sales", json=data, headers=key)).status_code == 409
    await client.patch(f"/api/v1/locations/{loc}", json={"is_active": True})
    sale = await client.post("/api/v1/servicing/sales", json=data, headers={**cashier, **key})
    assert sale.status_code == 201, sale.text
    assert Decimal(sale.json()["amount_usd"]) == 0


async def test_concurrent_checkouts_only_post_once(client):
    loc = await location(client)
    service = await create(client, status="finished")
    data = {"barcode": service["barcode"], "location_id": loc, "cost": "25"}
    responses = await asyncio.gather(
        *[
            client.post("/api/v1/servicing/sales", json=data, headers={"Idempotency-Key": str(n)})
            for n in range(2)
        ]
    )
    assert sorted(r.status_code for r in responses) == [201, 409]
    entries = (await client.get("/api/v1/cash/entries", params={"location_id": loc})).json()
    assert len(entries) == 1


@pytest.mark.parametrize("cost", ["-0.01", "1.234", "1000000000000.00", "NaN", "Infinity"])
async def test_service_checkout_rejects_invalid_amounts(client, cost):
    response = await client.post(
        "/api/v1/servicing/sales",
        json={"barcode": "SV1", "location_id": 1, "cost": cost},
        headers={"Idempotency-Key": "invalid"},
    )
    assert response.status_code == 422


async def test_exact_lookup_reserved_characters_and_legacy_estimate_not_collected(
    client, test_session_factory
):
    barcode = "REPAIR/1?A&B"
    async with test_session_factory() as db:
        db.add(
            InventoryService(
                barcode=barcode, status="finished", cost=Decimal("100"), unit="showroom"
            )
        )
        await db.commit()
    found = await client.get("/api/v1/servicing", params={"barcode": barcode})
    assert found.status_code == 200 and len(found.json()) == 1
    assert found.json()[0]["sale"] is None
    assert (await client.get("/api/v1/servicing", params={"barcode": "REPAIR"})).json() == []
    for invalid in ["", "x" * 51]:
        assert (
            await client.get("/api/v1/servicing", params={"barcode": invalid})
        ).status_code == 422
    month = datetime.now(UTC).strftime("%Y-%m")
    report = (await client.get("/api/v1/operations/profit", params={"month": month})).json()
    assert Decimal(report["service_sales_usd"]) == 0


async def test_service_income_is_scoped_by_workspace_location_and_collection_month(client):
    loc = await location(client)
    other = (
        await client.post("/api/v1/locations", json={"name": "Other", "code": "OTHER"})
    ).json()["id"]
    month = datetime.now(UTC).strftime("%Y-%m")
    for unit, paid in [("factory", "40"), ("showroom", "15")]:
        workspace = {"X-Business-Unit": unit}
        service = await create(client, status="finished", headers=workspace)
        response = await client.post(
            "/api/v1/servicing/sales",
            json={
                "barcode": service["barcode"],
                "location_id": loc,
                "cost": paid,
            },
            headers={**workspace, "Idempotency-Key": "same-key-in-each-workspace"},
        )
        assert response.status_code == 201, response.text
        for path in ["/api/v1/operations/profit", "/api/v1/insights/monthly-profit"]:
            report = (
                await client.get(
                    path, params={"month": month, "location_id": loc}, headers=workspace
                )
            ).json()
            assert Decimal(report["service_sales_usd"]) == Decimal(paid)
            empty = (
                await client.get(
                    path, params={"month": month, "location_id": other}, headers=workspace
                )
            ).json()
            assert Decimal(empty["service_sales_usd"]) == 0
            previous = (
                await client.get(path, params={"month": "2000-01"}, headers=workspace)
            ).json()
            assert Decimal(previous["service_sales_usd"]) == 0
        sales = await client.get(
            "/api/v1/servicing/sales", params={"location_id": other}, headers=workspace
        )
        assert sales.json() == []
        assert (
            len(
                (
                    await client.get(
                        "/api/v1/servicing/sales", params={"location_id": loc}, headers=workspace
                    )
                ).json()
            )
            == 1
        )
    company = (
        await client.get("/api/v1/operations/profit", params={"month": month, "company": True})
    ).json()
    assert Decimal(company["service_sales_usd"]) == Decimal("55")
    assert Decimal(company["profit_usd"]) == Decimal("55")
