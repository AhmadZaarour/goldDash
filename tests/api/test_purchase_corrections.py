from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import InventoryBalance, InventoryItem, Purchase, SupplierLedgerEntry
from tests.api.test_backend_access import headers_for
from tests.api.test_customer_pricing import purchase_bulk
from tests.api.test_gold_workflows import invoice, setup_shop

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_admin_can_correct_then_void_unmoved_item_purchase(client, test_session_factory):
    shop = await setup_shop(client, test_session_factory)
    payload = invoice(shop)
    key = {"Idempotency-Key": "invoice-correction"}
    posted = await client.post("/api/v1/purchases/item", json=payload, headers=key)
    assert posted.status_code == 201, posted.text
    purchase_id = posted.json()["id"]
    path = f"/api/v1/purchases/{purchase_id}"

    cashier = await headers_for(test_session_factory, "cashier")
    assert (
        await client.patch(path, json={"invoice_number": "WRONG"}, headers=cashier)
    ).status_code == 403
    assert (
        await client.post(f"{path}/void", json={"reason": "Wrong order"}, headers=cashier)
    ).status_code == 403
    assert (
        await client.patch(
            path, json={"invoice_number": "OTHER"}, headers={"X-Business-Unit": "factory"}
        )
    ).status_code == 404
    assert (await client.patch(path, json={"location_id": shop["location"]})).status_code == 422
    amended = await client.patch(path, json={"invoice_number": "INV-001", "notes": "  Corrected "})
    assert amended.status_code == 200, amended.text
    assert amended.json()["invoice_number"] == "INV-001"
    assert amended.json()["notes"] == "Corrected"

    reason = {"reason": "Duplicate supplier invoice"}
    result = await client.post(f"{path}/void", json=reason)
    assert result.status_code == 200, result.text
    assert result.json()["voided_at"]
    assert result.json()["void_reason"] == reason["reason"]
    assert (await client.post(f"{path}/void", json=reason)).json() == result.json()
    assert (await client.patch(path, json={"notes": "Closed"})).status_code == 409
    replayed = await client.post("/api/v1/purchases/item", json=payload, headers=key)
    assert replayed.status_code == 201
    assert replayed.json()["id"] == purchase_id
    assert (await client.get(path)).json()["voided_at"] == result.json()["voided_at"]

    async with test_session_factory() as db:
        items = (await db.scalars(select(InventoryItem))).all()
        assert len(items) == 2
        assert {item.status for item in items} == {"voided"}
        entries = (
            await db.scalars(select(SupplierLedgerEntry).order_by(SupplierLedgerEntry.id))
        ).all()
        assert len(entries) == 2
        assert entries[1].reversal_of_id == entries[0].id
        assert entries[1].gold_24k == -entries[0].gold_24k
        assert entries[1].making_usd == -entries[0].making_usd


async def test_invoiced_pieces_with_linked_sales_cannot_be_voided(client, test_session_factory):
    shop = await setup_shop(client, test_session_factory)
    posted = await client.post("/api/v1/purchases/item", json=invoice(shop))
    purchase_id = posted.json()["id"]
    listing = await client.get("/api/v1/inventory/items", params={"purchase_id": purchase_id})
    item_id = listing.json()[0]["id"]
    sold = await client.post(
        "/api/v1/sales/item",
        json={
            "location_id": shop["location"],
            "items": [{"inventory_item_id": item_id, "discount": "0", "sell_price": "500"}],
        },
    )
    assert sold.status_code == 201, sold.text
    sale_lines = (await client.get(f"/api/v1/sales/item/{sold.json()['id']}")).json()
    returned = await client.post(
        "/api/v1/inventory/returns",
        json={
            "sale_item_id": sale_lines[0]["id"],
            "location_id": shop["location"],
            "refund_usd": "500",
        },
    )
    assert returned.status_code == 201, returned.text
    result = await client.post(
        f"/api/v1/purchases/{purchase_id}/void", json={"reason": "Entered by mistake"}
    )
    assert result.status_code == 409, result.text
    available = await client.get("/api/v1/inventory/items", params={"purchase_id": purchase_id})
    assert {item["status"] for item in available.json()} == {"in_stock"}


async def test_void_records_signed_supplier_activity_in_its_own_month(client, test_session_factory):
    shop = await setup_shop(client, test_session_factory)
    posted = await client.post("/api/v1/purchases/item", json=invoice(shop))
    assert posted.status_code == 201
    purchase_id = posted.json()["id"]
    async with test_session_factory() as db:
        purchase = await db.get(Purchase, purchase_id)
        purchase.created_at = datetime(2020, 6, 15, tzinfo=UTC)
        await db.commit()
    result = await client.post(
        f"/api/v1/purchases/{purchase_id}/void", json={"reason": "Supplier cancellation"}
    )
    assert result.status_code == 200, result.text
    posted_month = (
        datetime.fromisoformat(result.json()["voided_at"])
        .astimezone(ZoneInfo(settings.report_timezone))
        .strftime("%Y-%m")
    )
    for month, sign in [("2020-06", 1), (posted_month, -1)]:
        report = await client.get("/api/v1/insights/monthly-profit", params={"month": month})
        assert report.status_code == 200, report.text
        entry = report.json()["supplier_purchases"][0]
        assert Decimal(entry["gold_grams"]) == Decimal(posted.json()["gold_debt_24k"]) * sign
        assert Decimal(entry["making_usd"]) == 100 * sign


@pytest.mark.parametrize(("unit", "amount"), [("showroom", "250"), ("factory", "0")])
async def test_bulk_void_uses_saved_credit_and_restores_drawer(
    client, test_session_factory, unit, amount
):
    shop = await setup_shop(client, test_session_factory)
    headers = {"X-Business-Unit": unit}
    posted = await purchase_bulk(client, shop, amount=amount, unit=unit)
    assert posted.status_code == 201, posted.text
    path = f"/api/v1/purchases/{posted.json()['id']}"
    result = await client.post(f"{path}/void", json={"reason": "Wrong weight"}, headers=headers)
    assert result.status_code == 200, result.text
    summary = await client.get(
        "/api/v1/cash/summary", params={"location_id": shop["location"]}, headers=headers
    )
    assert Decimal(summary.json()["net_usd"]) == (1000 if unit == "showroom" else 0)
    assert Decimal(summary.json()["adjustments_usd"]) == Decimal(amount)
    async with test_session_factory() as db:
        balance = await db.scalar(
            select(InventoryBalance).where(
                InventoryBalance.unit == unit,
                InventoryBalance.placement == unit,
                InventoryBalance.purity_id == shop["p18"],
            )
        )
        assert balance.total_weight == balance.cost_usd == 0


async def test_bulk_void_rejects_changed_stock_bucket(client, test_session_factory):
    shop = await setup_shop(client, test_session_factory)
    first = await purchase_bulk(client, shop)
    second = await purchase_bulk(client, shop)
    assert first.status_code == second.status_code == 201
    result = await client.post(
        f"/api/v1/purchases/{first.json()['id']}/void", json={"reason": "Wrong weight"}
    )
    assert result.status_code == 409, result.text
    summary = await client.get("/api/v1/cash/summary", params={"location_id": shop["location"]})
    assert Decimal(summary.json()["net_usd"]) == 500
