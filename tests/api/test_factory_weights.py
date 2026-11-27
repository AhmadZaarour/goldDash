"""Weight-only production conserves gold, valuation, receivables and ownership."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models import GoldPurity, InventoryItem, ProductionPiece
from tests.api.test_backend_access import headers_for
from tests.api.test_workspaces import header, overview, seed, shop

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def setup(client, factory):
    s = await shop(factory)
    async with factory() as db:
        p24 = await db.scalar(select(GoldPurity).where(GoldPurity.karat == 24))
        p21 = GoldPurity(name="21K", karat=21, purity=Decimal("87.5"))
        db.add(p21)
        await db.commit()
        s["p24"], s["p21"] = p24.id, p21.id
    s["raw"] = s["purity"]
    await seed(client, {**s, "purity": s["p24"]}, "factory", "1000", "100", "5000")
    return s


async def start(client, s, key=None):
    response = await client.post(
        "/api/v1/operations/weight-production",
        json={
            "location_id": s["location"],
            "reference": "Batch 100",
            "inputs": [{"purity_id": s["p24"], "weight": "100"}],
            "direct_cost_usd": "10",
        },
        headers=header("factory", key),
    )
    assert response.status_code == 201, response.text
    return response


async def step(
    client, batch, s, *, index=0, weight="60", note="Measured loss", scrap="0", key=None
):
    return await client.post(
        f"/api/v1/operations/weight-production/{batch}/steps",
        json={
            "name": "Alloying" if index == 0 else "Polishing",
            "expected_step": index,
            "outputs": [
                {"purity_id": s["purity"], "weight": weight},
                {"purity_id": s["p21"], "weight": "60"},
            ],
            "scrap": [] if scrap == "0" else [{"purity_id": s["p24"], "weight": scrap}],
            "note": note,
            "direct_cost_usd": "5",
        },
        headers=header("factory", key),
    )


async def finish(client, batch, count=1):
    return await client.post(
        f"/api/v1/operations/weight-production/{batch}/finish",
        json={"expected_step": count},
        headers=header("factory"),
    )


async def details(client, batch):
    return (
        await client.get(f"/api/v1/operations/production/{batch}", headers=header("factory"))
    ).json()


async def stock(client, unit="factory"):
    response = await client.get("/api/v1/operations/finished-stock", headers=header(unit))
    assert response.status_code == 200, response.text
    return response.json()


async def completed(client, s):
    batch = (await start(client, s)).json()["id"]
    response = await step(client, batch, s, scrap="1")
    assert response.status_code == 201, response.text
    response = await finish(client, batch)
    assert response.status_code == 201, response.text
    return batch


async def test_weight_production_steps_track_actual_gold_not_alloy_weight(
    client, test_session_factory
):
    s = await setup(client, test_session_factory)
    first, replay = await start(client, s, "start"), await start(client, s, "start")
    assert first.json() == replay.json()
    batch = first.json()["id"]
    assert Decimal((await overview(client, s, "factory"))["bulk"][0]["total_weight"]) == 0
    assert await stock(client) == []
    measured = await step(client, batch, s, scrap="1", key="step")
    assert measured.status_code == 201, measured.text
    assert (await step(client, batch, s, scrap="1", key="step")).json() == measured.json()
    record = await details(client, batch)
    # Physical output is 120g after alloying, yet its gold content is below 100g 24K.
    output = Decimal("60") * (Decimal("75") + Decimal("87.5")) / Decimal("99.5")
    assert abs(Decimal(record["output_gold_24k"]) - output) <= Decimal("0.000001")
    assert abs(Decimal(record["loss_gold_24k"]) - (100 - output - 1)) <= Decimal("0.000001")
    assert (await step(client, batch, s, index=1, weight="59.9")).status_code == 201
    record = await details(client, batch)
    assert len(record["details"]["steps"]) == 2
    assert Decimal(record["loss_gold_24k"]) > Decimal(measured.json()["loss_gold_24k"])
    assert await stock(client) == []
    assert (await finish(client, batch, 1)).status_code == 409
    assert (await finish(client, batch, 2)).status_code == 201
    rows = await stock(client)
    assert {r["purity_id"]: Decimal(str(r["weight"])) for r in rows} == {
        s["purity"]: Decimal("59.9"),
        s["p21"]: Decimal("60"),
    }
    assert sum(Decimal(str(r["cost_usd"])) for r in rows) == Decimal("4970")
    assert Decimal((await overview(client, s, "factory"))["bulk"][0]["cost_usd"]) == 50
    assert Decimal((await overview(client, s, "factory"))["cash_usd"]) == 980
    async with test_session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(InventoryItem)) == 0
        assert await db.scalar(select(func.count()).select_from(ProductionPiece)) == 0
    assert (await step(client, batch, s, index=2)).status_code == 409
    assert (await finish(client, batch, 2)).status_code == 409


async def test_admin_can_correct_production_and_reverse_latest_step(client, test_session_factory):
    s = await setup(client, test_session_factory)
    batch = (await start(client, s)).json()["id"]
    batch_url = f"/api/v1/operations/production/{batch}"
    steps_url = f"/api/v1/operations/weight-production/{batch}/steps"
    corrected = {"reference": "Corrected reference", "note": "Technician corrected the label"}
    employee = await headers_for(test_session_factory, "employee")
    assert (
        await client.patch(batch_url, json=corrected, headers={**header("factory"), **employee})
    ).status_code == 403
    assert (
        await client.patch(batch_url, json=corrected, headers=header("factory"))
    ).status_code == 200

    assert (await step(client, batch, s, scrap="1")).status_code == 201
    before = await details(client, batch)
    assert before["reference"] == corrected["reference"]
    assert (await step(client, batch, s, index=1, weight="59.9")).status_code == 201
    original = (await details(client, batch))["details"]["steps"]
    old_timestamp = original[1]["created_at"]
    change = {
        "name": "Corrected polishing",
        "note": "Measured loss after polishing",
        "expected_created_at": old_timestamp,
    }
    updated = await client.patch(f"{steps_url}/2", json=change, headers=header("factory"))
    assert updated.status_code == 200, updated.text
    edited = (await details(client, batch))["details"]["steps"][1]
    assert edited == {**original[1], "name": change["name"], "note": change["note"]}

    data = {"note": "Redo final measurements", "expected_created_at": original[0]["created_at"]}
    previous = await client.post(f"{steps_url}/1/reverse", json=data, headers=header("factory"))
    assert previous.status_code == 409
    data["expected_created_at"] = old_timestamp
    reverse_header = header("factory", "undo-step")
    reversed_step = await client.post(f"{steps_url}/2/reverse", json=data, headers=reverse_header)
    assert reversed_step.status_code == 201, reversed_step.text
    assert (
        await client.post(f"{steps_url}/2/reverse", json=data, headers=reverse_header)
    ).json() == reversed_step.json()
    assert (await details(client, batch)) == before
    assert Decimal((await overview(client, s, "factory"))["cash_usd"]) == 985
    assert await stock(client) == []

    assert (await step(client, batch, s, index=1, weight="59.8")).status_code == 201
    stale_finish = await client.post(
        f"/api/v1/operations/weight-production/{batch}/finish",
        json={"expected_step": 2, "expected_step_created_at": old_timestamp},
        headers=header("factory"),
    )
    assert stale_finish.status_code == 409
    result = await client.post(
        f"{batch_url}/reverse", json={"note": "Cancel run"}, headers=header("factory")
    )
    assert result.status_code == 201, result.text
    summary = await overview(client, s, "factory")
    assert Decimal(summary["cash_usd"]) == 1000
    assert Decimal(summary["bulk"][0]["total_weight"]) == 100


async def test_invalid_production_does_not_lose_raw_stock_or_cash(client, test_session_factory):
    s = await setup(client, test_session_factory)
    batch = (await start(client, s)).json()["id"]
    assert (await finish(client, batch)).status_code == 409
    assert (await step(client, batch, s, weight="100")).status_code == 409
    assert (await step(client, batch, s, note=None)).status_code == 409
    assert (await step(client, batch, s, index=1)).status_code == 409
    assert (await details(client, batch))["details"]["steps"] == []
    assert Decimal((await overview(client, s, "factory"))["cash_usd"]) == 990
    reverse = await client.post(
        f"/api/v1/operations/production/{batch}/reverse",
        json={"note": "Entered wrong input"},
        headers=header("factory"),
    )
    assert reverse.status_code == 201, reverse.text
    assert Decimal((await overview(client, s, "factory"))["bulk"][0]["total_weight"]) == 100
    assert Decimal((await overview(client, s, "factory"))["cash_usd"]) == 1000


async def test_finished_production_reversal_restores_exact_values_and_all_costs(
    client, test_session_factory
):
    s = await setup(client, test_session_factory)
    batch = await completed(client, s)
    response = await client.post(
        f"/api/v1/operations/production/{batch}/reverse",
        json={"note": "Correction"},
        headers=header("factory"),
    )
    assert response.status_code == 201, response.text
    assert await stock(client) == []
    state = await overview(client, s, "factory")
    assert Decimal(state["cash_usd"]) == 1000
    assert Decimal(state["bulk"][0]["total_weight"]) == 100
    assert Decimal(state["bulk"][0]["cost_usd"]) == 5000


async def test_supplier_weight_sale_uses_physical_grams_times_making_and_24k_ledger(
    client, test_session_factory
):
    s = await setup(client, test_session_factory)
    batch = await completed(client, s)
    data = {
        "location_id": s["location"],
        "supplier_id": s["supplier"],
        "lines": [
            {"purity_id": s["purity"], "weight": "10", "making_per_gram": "2.5"},
            {"purity_id": s["p21"], "weight": "5", "making_per_gram": "3"},
        ],
    }
    response = await client.post(
        "/api/v1/operations/supplier-weight-sales", json=data, headers=header("factory", "sale")
    )
    assert response.status_code == 201, response.text
    assert (
        await client.post(
            "/api/v1/operations/supplier-weight-sales", json=data, headers=header("factory", "sale")
        )
    ).json() == response.json()
    assert Decimal(response.json()["making_usd"]) == 40
    assert Decimal(response.json()["gold_24k"]) == Decimal("11.935")
    balance = (
        await client.get(f"/api/v1/suppliers/{s['supplier']}/balance", headers=header("factory"))
    ).json()
    assert Decimal(balance["gold_24k"]) == Decimal("-11.935")
    assert Decimal(balance["making_usd"]) == -40
    assert Decimal((await overview(client, s, "factory"))["cash_usd"]) == 985
    rows = await stock(client)
    assert {r["purity_id"]: Decimal(str(r["weight"])) for r in rows} == {
        s["purity"]: 50,
        s["p21"]: 55,
    }
    lines = (
        await client.get(
            f"/api/v1/operations/supplier-weight-sales/{response.json()['id']}",
            headers=header("factory"),
        )
    ).json()
    assert len(lines) == 2
    month = datetime.now(UTC).strftime("%Y-%m")
    report = (
        await client.get(
            "/api/v1/operations/profit", params={"month": month}, headers=header("factory")
        )
    ).json()
    assert Decimal(report["revenue_usd"]) == sum(
        Decimal(line["total_value_usd"]) for line in lines
    ).quantize(Decimal("0.01"))
    assert Decimal(report["cost_of_sales_usd"]) == sum(
        Decimal(line["cost_usd"]) for line in lines
    ).quantize(Decimal("0.01"))
    insight_response = await client.get(
        "/api/v1/insights/monthly-profit", params={"month": month}, headers=header("factory")
    )
    assert insight_response.status_code == 200, insight_response.text
    trades = insight_response.json()["supplier_sales"]
    assert sum(Decimal(row["weight_grams"]) for row in trades) == 15
    assert sum(Decimal(row["settlement_grams"]) for row in trades) == Decimal("11.935")
    assert sum(Decimal(row["making_usd"]) for row in trades) == 40
    showroom_insights = (
        await client.get(
            "/api/v1/insights/monthly-profit", params={"month": month}, headers=header("showroom")
        )
    ).json()
    assert showroom_insights["supplier_sales"] == []
    assert (
        await client.post(
            f"/api/v1/operations/production/{batch}/reverse",
            json={"note": "Used stock"},
            headers=header("factory"),
        )
    ).status_code == 409
    assert (
        await client.get(
            f"/api/v1/operations/supplier-weight-sales/{response.json()['id']}",
            headers=header("showroom"),
        )
    ).status_code == 404


async def supply(client, s, weight="10", key=None):
    return await client.post(
        "/api/v1/operations/weight-internal-invoices",
        json={
            "location_id": s["location"],
            "showroom_location_id": s["location"],
            "gold_price_usd": "100",
            "lines": [{"purity_id": s["purity"], "weight": weight, "making_per_gram": "2"}],
        },
        headers=header("factory", key),
    )


async def test_showroom_receives_weight_then_registers_pieces_with_exact_company_cost(
    client, test_session_factory
):
    s = await setup(client, test_session_factory)
    await completed(client, s)
    invoice = await supply(client, s)
    assert invoice.status_code == 201, invoice.text
    invoice_id = invoice.json()["id"]
    assert (await client.get("/api/v1/inventory/items", headers=header("showroom"))).json() == []
    pending = (
        await client.get("/api/v1/operations/pending-receipts", headers=header("showroom"))
    ).json()
    assert Decimal(pending[0]["remaining_weight"]) == 10
    receive = {
        "pieces": [
            {"product_id": s["item"], "weight": "4"},
            {"product_id": s["item"], "weight": "6"},
        ]
    }
    response = await client.post(
        f"/api/v1/operations/weight-internal-invoices/{invoice_id}/receive",
        json=receive,
        headers=header("showroom", "receipt"),
    )
    assert response.status_code == 201, response.text
    assert len(response.json()["inventory_item_ids"]) == 2
    assert (
        await client.post(
            f"/api/v1/operations/weight-internal-invoices/{invoice_id}/receive",
            json=receive,
            headers=header("showroom", "receipt"),
        )
    ).json() == response.json()
    assert (
        await client.get("/api/v1/operations/pending-receipts", headers=header("showroom"))
    ).json() == []
    showroom = (await client.get("/api/v1/inventory/items", headers=header("showroom"))).json()
    assert len(showroom) == 2 and len({row["barcode"] for row in showroom}) == 2
    assert sum(Decimal(row["base_cost_usd"]) for row in showroom) == Decimal("773.80")
    extra = await client.post(
        f"/api/v1/operations/weight-internal-invoices/{invoice_id}/receive",
        json={"pieces": [{"product_id": s["item"], "weight": "0.001"}]},
        headers=header("showroom"),
    )
    assert extra.status_code == 409
    assert (
        await client.post(
            f"/api/v1/operations/internal-invoices/{invoice_id}/reverse",
            json={"note": "Already registered"},
            headers=header("factory"),
        )
    ).status_code == 409
    # Internal gold and making charges remain payable under the existing equations.
    balance = (
        await client.get("/api/v1/operations/internal-balance", headers=header("showroom"))
    ).json()
    assert Decimal(balance["gold_24k"]) == Decimal("7.538")
    assert Decimal(balance["making_usd"]) == 20
    async with test_session_factory() as db:
        items = list(await db.scalars(select(InventoryItem)))
        company_cost = sum(item.company_cost_usd for item in items)
        own_cost = sum(item.owner_cost_usd for item in items)
        assert company_cost < own_cost


async def test_internal_weight_supply_reversal_restores_original_lots(client, test_session_factory):
    s = await setup(client, test_session_factory)
    await completed(client, s)
    before = await stock(client)
    invoice = await supply(client, s)
    assert invoice.status_code == 201
    invoice_url = f"/api/v1/operations/internal-invoices/{invoice.json()['id']}"
    note = {"note": "Corrected dispatch description"}
    edit = await client.patch(invoice_url, json=note, headers=header("factory"))
    assert edit.status_code == 200, edit.text
    invoices = await client.get("/api/v1/operations/internal-invoices", headers=header("showroom"))
    assert invoices.json()[0]["note"] == note["note"]
    response = await client.post(
        f"{invoice_url}/reverse",
        json={"note": "Supply correction"},
        headers=header("showroom"),
    )
    assert response.status_code == 201, response.text
    assert (
        await client.patch(invoice_url, json=note, headers=header("factory"))
    ).status_code == 409
    invoices = await client.get("/api/v1/operations/internal-invoices", headers=header("showroom"))
    assert invoices.json()[1]["is_reversed"] is True
    assert await stock(client) == before
    assert (
        await client.get("/api/v1/operations/pending-receipts", headers=header("showroom"))
    ).json() == []


async def test_finished_stock_concurrent_sales_cannot_oversell(client, test_session_factory):
    s = await setup(client, test_session_factory)
    await completed(client, s)
    data = {
        "location_id": s["location"],
        "supplier_id": s["supplier"],
        "lines": [{"purity_id": s["purity"], "weight": "40", "making_per_gram": "0"}],
    }
    results = await asyncio.gather(
        *[
            client.post(
                "/api/v1/operations/supplier-weight-sales", json=data, headers=header("factory")
            )
            for _ in range(2)
        ]
    )
    assert sorted(r.status_code for r in results) == [201, 409], [r.text for r in results]
    state = await stock(client)
    assert Decimal(str(next(r for r in state if r["purity_id"] == s["purity"])["weight"])) == 20


async def test_finished_seed_requires_explicit_values_and_roles(client, test_session_factory):
    s = await shop(test_session_factory)
    employee = {**await headers_for(test_session_factory, "employee"), **header("factory")}
    data = {
        "location_id": s["location"],
        "gold": [{"purity_id": s["purity"], "weight": "10", "value_usd": "0"}],
        "note": "Initial finished stock",
    }
    assert (
        await client.post("/api/v1/operations/finished-opening", json=data, headers=employee)
    ).status_code == 403
    response = await client.post(
        "/api/v1/operations/finished-opening", json=data, headers=header("factory")
    )
    assert response.status_code == 201, response.text
    assert Decimal(str((await stock(client))[0]["weight"])) == 10
    assert (
        await client.post(
            "/api/v1/operations/finished-opening", json=data, headers=header("showroom")
        )
    ).status_code == 403


async def test_concurrent_steps_and_cross_workspace_permissions(client, test_session_factory):
    s = await setup(client, test_session_factory)
    batch = (await start(client, s)).json()["id"]
    results = await asyncio.gather(step(client, batch, s), step(client, batch, s))
    assert sorted(r.status_code for r in results) == [201, 409]
    assert len((await details(client, batch))["details"]["steps"]) == 1
    assert Decimal((await overview(client, s, "factory"))["cash_usd"]) == 985
    cashier = {**await headers_for(test_session_factory, "cashier"), **header("factory")}
    assert (
        await client.post("/api/v1/operations/weight-production", json={}, headers=cashier)
    ).status_code == 403
    assert (
        await client.post("/api/v1/operations/supplier-weight-sales", json={}, headers=cashier)
    ).status_code == 403
    body = {"location_id": s["location"], "inputs": [{"purity_id": s["p24"], "weight": "1"}]}
    assert (
        await client.post(
            "/api/v1/operations/weight-production", json=body, headers=header("showroom")
        )
    ).status_code == 403


async def test_company_margin_keeps_production_cost_when_showroom_sells_received_piece(
    client, test_session_factory
):
    s = await setup(client, test_session_factory)
    await completed(client, s)
    invoice = await supply(client, s)
    invoice_id = invoice.json()["id"]
    receipt = await client.post(
        f"/api/v1/operations/weight-internal-invoices/{invoice_id}/receive",
        json={"pieces": [{"product_id": s["item"], "weight": "4"}]},
        headers=header("showroom"),
    )
    assert receipt.status_code == 201, receipt.text
    item_id = receipt.json()["inventory_item_ids"][0]
    async with test_session_factory() as db:
        item = await db.get(InventoryItem, item_id)
        company_cost, showroom_cost = item.company_cost_usd, item.owner_cost_usd
    sale = await client.post(
        "/api/v1/sales/item",
        json={
            "location_id": s["location"],
            "items": [{"inventory_item_id": item_id, "sell_price": "500", "discount": "0"}],
        },
        headers=header("showroom"),
    )
    assert sale.status_code == 201, sale.text
    params = {"month": datetime.now(UTC).strftime("%Y-%m")}
    own = (
        await client.get("/api/v1/operations/profit", params=params, headers=header("showroom"))
    ).json()
    company = (
        await client.get(
            "/api/v1/operations/profit",
            params={**params, "company": True},
            headers=header("factory"),
        )
    ).json()
    assert Decimal(own["profit_usd"]) == (500 - showroom_cost).quantize(Decimal("0.01"))
    assert Decimal(company["profit_usd"]) == (500 - company_cost).quantize(Decimal("0.01"))
    assert Decimal(company["internal_sales_usd"]) == 0


async def test_invoice_rounds_making_charge_once_and_finished_seed_can_reverse(
    client, test_session_factory
):
    s = await setup(client, test_session_factory)
    await completed(client, s)
    sale = await client.post(
        "/api/v1/operations/supplier-weight-sales",
        json={
            "location_id": s["location"],
            "supplier_id": s["supplier"],
            "lines": [
                {"purity_id": s["purity"], "weight": "0.005", "making_per_gram": "1"},
                {"purity_id": s["p21"], "weight": "0.005", "making_per_gram": "1"},
            ],
        },
        headers=header("factory"),
    )
    assert sale.status_code == 201, sale.text
    assert Decimal(sale.json()["making_usd"]) == Decimal("0.01")
    data = {
        "location_id": s["location"],
        "gold": [{"purity_id": s["purity"], "weight": "10", "value_usd": "0"}],
        "note": "Initial finished gold",
    }
    seed_response = await client.post(
        "/api/v1/operations/finished-opening", json=data, headers=header("factory")
    )
    assert seed_response.status_code == 201
    url = f"/api/v1/operations/history/{seed_response.json()['id']}/reverse"
    assert (
        await client.post(url, json={"note": "Correct seed"}, headers=header("factory"))
    ).status_code == 201
    assert (
        await client.post(url, json={"note": "Again"}, headers=header("factory"))
    ).status_code == 409


async def test_admin_can_stage_only_pending_showroom_receipt_photos(
    client,
    test_session_factory,
    tmp_path,
    monkeypatch,
):
    from app.core.config import settings
    from tests.api.test_item_photos import jpeg

    monkeypatch.setattr(settings, "item_image_dir", str(tmp_path))
    s = await setup(client, test_session_factory)
    await completed(client, s)
    invoice = await supply(client, s)
    employee = await headers_for(test_session_factory, "employee")
    showroom_employee = {**employee, **header("showroom")}
    invoice_id = invoice.json()["id"]
    photo_url = f"/api/v1/operations/weight-internal-invoices/{invoice_id}/photos"
    assert (
        await client.post(photo_url, content=jpeg(), headers=showroom_employee)
    ).status_code == 403
    receipt_url = f"/api/v1/operations/weight-internal-invoices/{invoice_id}/receive"
    assert (
        await client.post(
            receipt_url,
            json={"pieces": [{"product_id": s["item"], "weight": "10"}]},
            headers=showroom_employee,
        )
    ).status_code == 403
    assert (
        await client.post(
            "/api/v1/operations/weight-internal-invoices/999999/photos",
            content=jpeg(),
            headers=header("showroom"),
        )
    ).status_code == 404
    assert (
        await client.post(photo_url, content=jpeg(), headers={**employee, **header("factory")})
    ).status_code == 403
    photo = await client.post(photo_url, content=jpeg(), headers=header("showroom"))
    assert photo.status_code == 201, photo.text
    response = await client.post(
        receipt_url,
        json={
            "pieces": [
                {"product_id": s["item"], "weight": "10", "photo_token": photo.json()["token"]}
            ]
        },
        headers=header("showroom"),
    )
    assert response.status_code == 201, response.text
    item_id = response.json()["inventory_item_ids"][0]
    item = (
        await client.get(f"/api/v1/inventory/items/{item_id}", headers=header("showroom"))
    ).json()
    assert item["image_url"].endswith(".jpg")
    assert (await client.get(item["image_url"], headers=header("showroom"))).status_code == 200
    assert (
        await client.post(photo_url, content=jpeg(), headers=header("showroom"))
    ).status_code == 409
