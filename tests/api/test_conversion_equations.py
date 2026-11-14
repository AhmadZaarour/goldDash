"""Public accounting examples for the four confirmed conversion equations."""

import asyncio
import runpy
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import InventoryBalance, SupplierLedgerEntry, User
from app.services.supplier_ledger_service import post_entry
from tests.api.test_gold_workflows import setup_shop

pytestmark = pytest.mark.asyncio(loop_scope="session")
MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "alembic/versions/d12026_explicit_item_gold_charge.py"
)


@pytest.mark.parametrize(
    "purity_key,product_key,expected",
    [("p18", "item18", "75.377"), ("p21", "item21", "87.940")],
)
async def test_100_grams_trade_equations(
    client, test_session_factory, purity_key, product_key, expected
):
    s = await setup_shop(client, test_session_factory)
    purchase = await client.post(
        "/api/v1/purchases/item",
        json={
            "supplier_id": s["supplier"],
            "location_id": s["location"],
            "total_gold_charge_grams": "100",
            "items": [
                {
                    "supplier_id": s["supplier"],
                    "product_id": s[product_key],
                    "weight": "100",
                    "making_charge": "50",
                }
            ],
        },
    )
    assert purchase.status_code == 201, purchase.text
    assert Decimal(purchase.json()["gold_debt_24k"]) == Decimal(expected)
    async with test_session_factory() as db:
        db.add(
            InventoryBalance(
                unit="factory",
                purity_id=s[purity_key],
                location_id=s["location"],
                placement="factory",
                total_weight=100,
                cost_usd=1000,
            )
        )
        await db.commit()
    sale = await client.post(
        "/api/v1/sales/stock",
        headers={"X-Business-Unit": "factory"},
        json={
            "location_id": s["location"],
            "item": {
                "supplier_id": s["supplier"],
                "gold_purity_id": s[purity_key],
                "weight": "100",
                "gold_charge_in_grams": "100",
                "making_charge": "50",
            },
        },
    )
    assert sale.status_code == 201, sale.text
    async with test_session_factory() as db:
        entries = list(
            await db.scalars(select(SupplierLedgerEntry).order_by(SupplierLedgerEntry.id))
        )
        assert [entry.gold_24k for entry in entries] == [Decimal(expected), -Decimal(expected)]
    balance = (await client.get(f"/api/v1/suppliers/{s['supplier']}/balance")).json()
    assert Decimal(balance["gold_24k"]) == Decimal(expected)
    assert Decimal(balance["making_usd"]) == 5000
    factory_balance = (
        await client.get(
            f"/api/v1/suppliers/{s['supplier']}/balance", headers={"X-Business-Unit": "factory"}
        )
    ).json()
    assert Decimal(factory_balance["gold_24k"]) == -Decimal(expected)
    assert Decimal(factory_balance["making_usd"]) == -50


@pytest.mark.parametrize(
    "purity_key,payment,remaining_stock,factor",
    [("p18", "135.135", "64.865", "0.74"), ("p21", "115.607", "84.393", "0.865")],
)
async def test_100_grams_24k_debt_repayment_equations(
    client, test_session_factory, purity_key, payment, remaining_stock, factor
):
    s = await setup_shop(client, test_session_factory)
    async with test_session_factory() as db:
        actor = await db.scalar(select(User))
        await post_entry(
            db,
            supplier_id=s["supplier"],
            purity_id=s["p24"],
            gold_grams=Decimal("100"),
            making_usd=0,
            source_key="equation-debt",
            kind="purchase",
            created_by=actor.id,
        )
        stock = await db.scalar(
            select(InventoryBalance).where(InventoryBalance.purity_id == s[purity_key])
        )
        stock.total_weight = Decimal("200")
        await db.commit()
    url = f"/api/v1/suppliers/{s['supplier']}"
    response = await client.post(
        url + "/settlements",
        json={
            "idempotency_key": "equation-payment",
            "direction": "sent",
            "location_id": s["location"],
            "purity_id": s[purity_key],
            "gold_grams": payment,
            "close_account": True,
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["is_settled"]
    assert Decimal(response.json()["gold_24k"]) == 0
    async with test_session_factory() as db:
        entry = await db.scalar(
            select(SupplierLedgerEntry).where(SupplierLedgerEntry.kind == "settlement")
        )
        assert entry.valuation_factor == Decimal(factor)
        assert entry.gold_24k == Decimal("-100")
        assert entry.physical_gold_grams == -Decimal(payment)
        stock = await db.scalar(
            select(InventoryBalance).where(InventoryBalance.purity_id == s[purity_key])
        )
        assert stock.total_weight == Decimal(remaining_stock)


async def mixed_example(client, factory):
    s = await setup_shop(client, factory)
    response = await client.post(
        "/api/v1/purchases/item",
        json={
            "supplier_id": s["supplier"],
            "location_id": s["location"],
            "total_gold_charge_grams": "7.5",
            "items": [
                {
                    "supplier_id": s["supplier"],
                    "product_id": s["item21"],
                    "weight": "5",
                    "making_charge": "0",
                },
                {
                    "supplier_id": s["supplier"],
                    "product_id": s["item18"],
                    "weight": "2.5",
                    "making_charge": "0",
                },
            ],
        },
    )
    assert response.status_code == 201, response.text
    return s, response.json()


async def test_5g_21k_mixed_invoice_never_becomes_5_25g(client, test_session_factory):
    s, purchase = await mixed_example(client, test_session_factory)
    lines = (await client.get(f"/api/v1/purchases/items/{purchase['id']}")).json()
    assert [Decimal(line["weight"]) for line in lines] == [Decimal("5"), Decimal("2.5")]
    assert [Decimal(line["gold_charge_in_grams"]) for line in lines] == [
        Decimal("5"),
        Decimal("2.5"),
    ]
    assert [Decimal(line["gold_charge_24k"]) for line in lines] == [
        Decimal("4.397"),
        Decimal("1.884"),
    ]
    assert (
        sum(Decimal(line["gold_charge_24k"]) for line in lines)
        == Decimal(purchase["gold_debt_24k"])
        == Decimal("6.281")
    )
    inventory = (
        await client.get("/api/v1/inventory/items", params={"purchase_id": purchase["id"]})
    ).json()
    assert Decimal(inventory[0]["weight"]) == 5
    assert Decimal(inventory[0]["gold_charge_24k"]) == Decimal("4.397")
    balance = (await client.get(f"/api/v1/suppliers/{s['supplier']}/balance")).json()
    assert Decimal(balance["gold_24k"]) == Decimal("6.281")


async def test_existing_invoice_charge_backfill_preserves_recorded_financials(
    client, test_session_factory
):

    from sqlalchemy import text

    from app.models import PurchaseItem

    s, purchase = await mixed_example(client, test_session_factory)
    url = f"/api/v1/suppliers/{s['supplier']}/balance"
    before = (await client.get(url)).json()
    async with test_session_factory() as db:
        lines = list(
            await db.scalars(
                select(PurchaseItem)
                .where(PurchaseItem.purchase_id == purchase["id"])
                .order_by(PurchaseItem.id)
            )
        )
        for line, old_charge in zip(lines, ["5.25", "2.25"], strict=True):
            line.gold_charge_in_grams = Decimal(old_charge)
            line.gold_charge_24k = None
        await db.flush()
        migration = await asyncio.to_thread(runpy.run_path, str(MIGRATION_PATH))
        await db.execute(text(migration["BACKFILL_SQL"]))
        await db.commit()
    lines = (await client.get(f"/api/v1/purchases/items/{purchase['id']}")).json()
    assert [Decimal(line["gold_charge_24k"]) for line in lines] == [
        Decimal("4.397"),
        Decimal("1.884"),
    ]
    assert [Decimal(line["gold_charge_in_grams"]) for line in lines] == [
        Decimal("5.25"),
        Decimal("2.25"),
    ]
    assert [Decimal(line["weight"]) for line in lines] == [Decimal("5"), Decimal("2.5")]
    assert (await client.get(url)).json() == before
