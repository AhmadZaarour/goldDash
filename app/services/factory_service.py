"""Weight-based production, finished stock, supplier sales and showroom receipts."""

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select

from app.core.workspace import active_unit
from app.models import (
    FactoryWeightLine,
    FinishedGoldLot,
    GoldPurity,
    InventoryMovement,
    Sale,
)
from app.models.operations import (
    InternalInvoice,
    InternalInvoiceLine,
    OperationDocument,
    ProductionBatch,
    ProductionPiece,
)
from app.schemas.inventory import InventoryItemCreate
from app.services.gold_conversion import canonical_purity, grams24, purchase_factor
from app.services.gold_price import get_quote, require_fresh_quote
from app.services.inventory_service import create_item
from app.services.operations_query_service import record
from app.services.product_inventory_type import validate_purchase_product
from app.services.supplier_ledger_service import post_entry
from app.services.transaction_validation import require_active_supplier
from app.services.workspace_stock import change_stock, lock_locations, value4

ZERO = Decimal(0)
MICRO = Decimal("0.000001")


def ops():
    from app.services import operations_service

    return operations_service


def money(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def gold6(value):
    return Decimal(value).quantize(MICRO, rounding=ROUND_HALF_UP)


async def measured(db, rows, factors=None):
    seen, result = set(), []
    for row in rows:
        if row.purity_id in seen:
            raise ValueError("Enter each purity once per section")
        seen.add(row.purity_id)
        purity = await db.get(GoldPurity, row.purity_id)
        if purity is None:
            raise ValueError("Purity not found")
        factor = (factors or {}).get(
            row.purity_id, purchase_factor(purity).quantize(Decimal("0.0000000001"))
        )
        result.append(
            {
                "purity_id": row.purity_id,
                "weight": str(row.weight),
                "valuation_factor": str(factor),
                "gold_24k": str(gold6(row.weight * factor)),
            }
        )
    return result


def total_gold(rows):
    return sum((Decimal(row["gold_24k"]) for row in rows), ZERO)


def new_lot(
    db,
    *,
    unit,
    location_id,
    purity_id,
    weight,
    cost,
    company_cost=None,
    factor,
    batch_id=None,
    invoice_id=None,
    operation_id=None,
):
    lot = FinishedGoldLot(
        unit=unit,
        location_id=location_id,
        purity_id=purity_id,
        batch_id=batch_id,
        invoice_id=invoice_id,
        operation_id=operation_id,
        weight=weight,
        remaining_weight=weight,
        cost_usd=cost,
        company_cost_usd=cost if company_cost is None else company_cost,
        remaining_cost_usd=cost,
        remaining_company_cost_usd=cost if company_cost is None else company_cost,
        valuation_factor=factor,
    )
    db.add(lot)
    return lot


async def consume(db, *, unit, location_id, purity_id, weight, invoice_id=None):
    statement = select(FinishedGoldLot).where(
        FinishedGoldLot.unit == unit,
        FinishedGoldLot.location_id == location_id,
        FinishedGoldLot.purity_id == purity_id,
        FinishedGoldLot.remaining_weight > 0,
    )
    if invoice_id is not None:
        statement = statement.where(FinishedGoldLot.invoice_id == invoice_id)
    lots = list(await db.scalars(statement.order_by(FinishedGoldLot.id).with_for_update()))
    if sum((lot.remaining_weight for lot in lots), ZERO) < weight:
        raise ValueError("Insufficient finished gold of this purity at this location")
    allocations, left, cost, company = [], weight, ZERO, ZERO
    for lot in lots:
        if not left:
            break
        take = min(left, lot.remaining_weight)
        own_value = (
            lot.remaining_cost_usd
            if take == lot.remaining_weight
            else value4(lot.remaining_cost_usd * take / lot.remaining_weight)
        )
        company_value = (
            lot.remaining_company_cost_usd
            if take == lot.remaining_weight
            else value4(lot.remaining_company_cost_usd * take / lot.remaining_weight)
        )
        lot.remaining_weight -= take
        lot.remaining_cost_usd -= own_value
        lot.remaining_company_cost_usd -= company_value
        allocations.append(
            {
                "lot_id": lot.id,
                "weight": str(take),
                "cost_usd": str(own_value),
                "company_cost_usd": str(company_value),
            }
        )
        cost += own_value
        company += company_value
        left -= take
    return cost, company, allocations


async def restore(db, allocations):
    for allocation in allocations:
        lot = await db.scalar(
            select(FinishedGoldLot)
            .where(FinishedGoldLot.id == allocation["lot_id"])
            .with_for_update()
        )
        lot.remaining_weight += Decimal(allocation["weight"])
        lot.remaining_cost_usd += Decimal(allocation["cost_usd"])
        lot.remaining_company_cost_usd += Decimal(allocation["company_cost_usd"])


async def start_production(db, data, user_id):
    await lock_locations(db, data.location_id)
    await ops().require_cash(db, "factory", data.location_id, data.direct_cost_usd)
    rows = await measured(db, data.inputs)
    material = ZERO
    for row in rows:
        value = await change_stock(
            db,
            unit="factory",
            location_id=data.location_id,
            purity_id=row["purity_id"],
            placement="factory",
            delta=-Decimal(row["weight"]),
        )
        if value is None:
            raise ValueError("Record the raw gold's carrying value before starting production")
        row["value_usd"] = str(value)
        row["placement"] = "factory"
        material += value
    doc = await ops().document(
        db,
        unit="factory",
        kind="production",
        location_id=data.location_id,
        user_id=user_id,
        note=data.note or data.reference or "Weight production",
        amount=data.direct_cost_usd,
    )
    batch = ProductionBatch(
        unit="factory",
        tracking_mode="weight",
        status="in_progress",
        location_id=data.location_id,
        reference=data.reference,
        note=data.note,
        material_cost_usd=material,
        direct_cost_usd=data.direct_cost_usd,
        total_cost_usd=material + data.direct_cost_usd,
        input_gold_24k=total_gold(rows),
        output_gold_24k=0,
        scrap_gold_24k=0,
        loss_gold_24k=0,
        operation_id=doc.id,
        gold_quote_at=None,
        created_by=user_id,
        details={"inputs": rows, "steps": [], "scrap": [], "cost_operations": [doc.id]},
    )
    db.add(batch)
    await db.flush()
    ops().cash_entry(db, doc, "factory", data.location_id, -data.direct_cost_usd, "production_cost")
    return {
        "id": batch.id,
        "kind": "production",
        "message": "Production started; input gold reserved",
    }


async def locked_batch(db, batch_id):
    batch = await db.get(ProductionBatch, batch_id)
    if batch is None or batch.tracking_mode != "weight":
        raise ValueError("Weight production batch not found")
    await lock_locations(db, batch.location_id)
    return await db.scalar(
        select(ProductionBatch)
        .where(ProductionBatch.id == batch_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def add_step(db, batch_id, data, user_id):
    batch = await locked_batch(db, batch_id)
    if batch.status != "in_progress":
        raise ValueError("Only an in-progress batch can receive production steps")
    steps = batch.details["steps"]
    if len(steps) != data.expected_step:
        raise ValueError("Production steps changed; reload the batch before recording another step")
    if len(steps) >= 100:
        raise ValueError("A batch supports at most 100 production steps")
    known = list(batch.details["inputs"])
    for saved in steps:
        known.extend(saved["outputs"] + saved["scrap"])
    factors = {row["purity_id"]: Decimal(row["valuation_factor"]) for row in known}
    outputs, scrap = (
        await measured(db, data.outputs, factors),
        await measured(db, data.scrap, factors),
    )
    previous = batch.input_gold_24k if not steps else Decimal(steps[-1]["output_gold_24k"])
    output_gold, scrap_gold = total_gold(outputs), total_gold(scrap)
    loss = gold6(previous - output_gold - scrap_gold)
    if loss < -MICRO:
        raise ValueError(
            "A step cannot create gold: outputs plus newly recovered scrap exceed its gold input"
        )
    loss = max(loss, ZERO)
    if loss > Decimal("0.001") and not (data.note or "").strip():
        raise ValueError("Explain the step's gold loss in its notes")
    await ops().require_cash(db, "factory", batch.location_id, data.direct_cost_usd)
    doc = await ops().document(
        db,
        unit="factory",
        kind="production",
        location_id=batch.location_id,
        user_id=user_id,
        note=data.note or data.name,
        amount=data.direct_cost_usd,
        details={"batch_id": batch.id, "step": len(steps) + 1},
    )
    ops().cash_entry(
        db, doc, "factory", batch.location_id, -data.direct_cost_usd, "production_cost"
    )
    step = {
        "name": data.name,
        "outputs": outputs,
        "scrap": scrap,
        "input_gold_24k": str(previous),
        "output_gold_24k": str(output_gold),
        "scrap_gold_24k": str(scrap_gold),
        "loss_gold_24k": str(loss),
        "direct_cost_usd": str(data.direct_cost_usd),
        "note": data.note,
        "created_by": user_id,
        "created_at": datetime.now(UTC).isoformat(),
    }
    batch.details = {
        **batch.details,
        "steps": [*steps, step],
        "cost_operations": [*batch.details["cost_operations"], doc.id],
    }
    batch.output_gold_24k = output_gold
    batch.scrap_gold_24k += scrap_gold
    batch.loss_gold_24k += loss
    batch.direct_cost_usd += data.direct_cost_usd
    batch.total_cost_usd += data.direct_cost_usd
    return {
        "id": batch.id,
        "kind": "production_step",
        "loss_gold_24k": str(loss),
        "message": "Production step recorded",
    }


async def finish_production(db, batch_id, data, user_id):
    batch = await locked_batch(db, batch_id)
    steps = batch.details["steps"]
    if batch.status != "in_progress" or not steps:
        raise ValueError("Record at least one step in an in-progress batch before finishing")
    if data.expected_step != len(steps):
        raise ValueError("Production steps changed; reload before finishing the batch")
    outputs = steps[-1]["outputs"]
    scrap = [row for step in steps for row in step["scrap"]]
    weights = [Decimal(row["gold_24k"]) for row in scrap]
    allocation_weights = [*weights, batch.input_gold_24k - sum(weights, ZERO)]
    values = ops().allocate_value(batch.material_cost_usd, allocation_weights)
    for row, value in zip(scrap, values[:-1], strict=True):
        row = {**row, "value_usd": str(value), "placement": "factory"}
        await change_stock(
            db,
            unit="factory",
            location_id=batch.location_id,
            purity_id=row["purity_id"],
            placement="factory",
            delta=Decimal(row["weight"]),
            value=value,
        )
    scrap = [
        {**row, "value_usd": str(value), "placement": "factory"}
        for row, value in zip(scrap, values[:-1], strict=True)
    ]
    batch.material_cost_usd = values[-1]
    batch.total_cost_usd = batch.material_cost_usd + batch.direct_cost_usd
    output_values = ops().allocate_value(
        batch.total_cost_usd, [Decimal(row["gold_24k"]) for row in outputs]
    )
    for row, value in zip(outputs, output_values, strict=True):
        new_lot(
            db,
            unit="factory",
            location_id=batch.location_id,
            purity_id=row["purity_id"],
            weight=Decimal(row["weight"]),
            cost=value,
            factor=Decimal(row["valuation_factor"]),
            batch_id=batch.id,
        )
    batch.details = {
        **batch.details,
        "scrap": scrap,
        "outputs": outputs,
        "finished_at": datetime.now(UTC).isoformat(),
        "finished_by": user_id,
    }
    batch.status = "active"
    return {
        "id": batch.id,
        "kind": "production_finished",
        "message": "Production finished; gold added to finished stock",
    }


async def reverse_production(db, batch_id, note, user_id):
    batch = await locked_batch(db, batch_id)
    if batch.status not in {"active", "in_progress"}:
        raise ValueError("Production batch already reversed")
    lots = list(
        await db.scalars(
            select(FinishedGoldLot).where(FinishedGoldLot.batch_id == batch.id).with_for_update()
        )
    )
    if any(lot.remaining_weight != lot.weight for lot in lots):
        raise ValueError(
            "Finished gold from this batch has already been used; reverse its supply first"
        )
    for lot in lots:
        lot.remaining_weight = ZERO
        lot.remaining_cost_usd = ZERO
        lot.remaining_company_cost_usd = ZERO
    for row in batch.details["scrap"]:
        await change_stock(
            db,
            unit="factory",
            location_id=batch.location_id,
            purity_id=row["purity_id"],
            placement="factory",
            delta=-Decimal(row["weight"]),
            value=Decimal(row["value_usd"]),
        )
    for row in batch.details["inputs"]:
        await change_stock(
            db,
            unit="factory",
            location_id=batch.location_id,
            purity_id=row["purity_id"],
            placement="factory",
            delta=Decimal(row["weight"]),
            value=Decimal(row["value_usd"]),
        )
    doc = await ops().document(
        db,
        unit="factory",
        kind="production_reversal",
        location_id=batch.location_id,
        user_id=user_id,
        note=note,
        amount=batch.direct_cost_usd,
        reversal_of_id=batch.operation_id,
    )
    ops().cash_entry(
        db, doc, "factory", batch.location_id, batch.direct_cost_usd, "production_cost"
    )
    batch.status = "reversed"
    return {"id": doc.id, "kind": "production_reversal", "message": "Production batch reversed"}


async def stock(db, location_id=None):
    statement = select(
        func.min(FinishedGoldLot.id).label("id"),
        FinishedGoldLot.purity_id,
        FinishedGoldLot.location_id,
        func.sum(FinishedGoldLot.remaining_weight).label("weight"),
        func.sum(FinishedGoldLot.remaining_cost_usd).label("cost_usd"),
        func.sum(FinishedGoldLot.remaining_company_cost_usd).label("company_cost_usd"),
    ).where(FinishedGoldLot.remaining_weight > 0)
    if location_id is not None:
        statement = statement.where(FinishedGoldLot.location_id == location_id)
    return [
        {key: str(value) if isinstance(value, Decimal) else value for key, value in row.items()}
        for row in (
            await db.execute(
                statement.group_by(FinishedGoldLot.purity_id, FinishedGoldLot.location_id).order_by(
                    FinishedGoldLot.location_id, FinishedGoldLot.purity_id
                )
            )
        ).mappings()
    ]


async def seed_finished(db, data, user_id):
    await lock_locations(db, data.location_id)
    if any(line.placement not in {None, "factory"} for line in data.gold):
        raise ValueError("Finished factory gold does not use raw-stock placements")
    if any(line.weight <= 0 or line.value_usd is None for line in data.gold):
        raise ValueError("Enter positive weights and explicit carrying values for finished gold")
    rows = await measured(db, data.gold)
    doc = await ops().document(
        db,
        unit="factory",
        kind="finished_opening",
        location_id=data.location_id,
        user_id=user_id,
        note=data.note,
        details={"gold": rows},
    )
    for row, line in zip(rows, data.gold, strict=True):
        new_lot(
            db,
            unit="factory",
            location_id=data.location_id,
            purity_id=line.purity_id,
            weight=line.weight,
            cost=value4(line.value_usd),
            factor=Decimal(row["valuation_factor"]),
            operation_id=doc.id,
        )
    return {"id": doc.id, "kind": "finished_opening", "message": "Finished gold balances recorded"}


def making_allocations(rows):
    raw = [row.weight * row.making_per_gram for row in rows]
    total = sum(raw, ZERO)
    if not total:
        return [ZERO for _ in rows]
    cents = int(money(total) * 100)
    shares = [Decimal(cents) * value / total for value in raw]
    whole = [int(value) for value in shares]
    order = sorted(range(len(rows)), key=lambda i: (-(shares[i] - whole[i]), i))
    for i in order[: cents - sum(whole)]:
        whole[i] += 1
    return [Decimal(value) / 100 for value in whole]


async def trade_rows(db, rows, location_id, price, *, invoice_id=None, sale_id=None):
    price = value4(price)
    measurements = await measured(db, rows)
    result = []
    for row, measurement, making in zip(rows, measurements, making_allocations(rows), strict=True):
        cost, company, allocations = await consume(
            db, unit="factory", location_id=location_id, purity_id=row.purity_id, weight=row.weight
        )
        charge = grams24(row.weight, Decimal(measurement["valuation_factor"]))
        line = FactoryWeightLine(
            sale_id=sale_id,
            invoice_id=invoice_id,
            purity_id=row.purity_id,
            weight=row.weight,
            gold_24k=charge,
            valuation_factor=Decimal(measurement["valuation_factor"]),
            making_per_gram=row.making_per_gram,
            making_usd=making,
            gold_price_usd=price,
            total_value_usd=value4(charge * price + making),
            cost_usd=cost,
            company_cost_usd=company,
            allocations=allocations,
        )
        db.add(line)
        result.append(line)
    return result


async def supplier_sale(db, data, user_id):
    await lock_locations(db, data.location_id)
    await require_active_supplier(db, data.supplier_id, exclusive=True)
    quote = await get_quote()
    require_fresh_quote(quote)
    sale = Sale(
        unit="factory",
        kind="supplier",
        supplier_id=data.supplier_id,
        invoice_number=data.invoice_number,
        location_id=data.location_id,
        notes=data.note,
        created_by=user_id,
        gold_quote_at=datetime.fromisoformat(quote["fetched_at"]),
    )
    db.add(sale)
    await db.flush()
    lines = await trade_rows(
        db, data.lines, data.location_id, Decimal(quote["gram_24k_usd"]), sale_id=sale.id
    )
    gold = sum((line.gold_24k for line in lines), ZERO)
    making = sum((line.making_usd for line in lines), ZERO)
    canonical = await canonical_purity(db)
    await post_entry(
        db,
        supplier_id=data.supplier_id,
        purity_id=canonical.id,
        gold_grams=-gold,
        gold_24k=-gold,
        making_usd=-making,
        source_key=f"supplier-weight:{sale.id}",
        kind="sale",
        created_by=user_id,
        sale_id=sale.id,
    )
    return {
        "id": sale.id,
        "kind": "supplier_weight_sale",
        "gold_24k": str(gold),
        "making_usd": str(making),
        "message": "Supplier weight sale recorded",
    }


async def supply_showroom(db, data, user_id):
    await lock_locations(db, data.location_id, data.showroom_location_id)
    invoice = InternalInvoice(
        tracking_mode="weight",
        factory_location_id=data.location_id,
        showroom_location_id=data.showroom_location_id,
        gold_24k=0,
        making_usd=0,
        gold_price_usd=data.gold_price_usd,
        total_value_usd=0,
        factory_cost_usd=0,
        note=data.note,
        created_by=user_id,
    )
    db.add(invoice)
    await db.flush()
    lines = await trade_rows(
        db, data.lines, data.location_id, data.gold_price_usd, invoice_id=invoice.id
    )
    invoice.gold_24k = sum((line.gold_24k for line in lines), ZERO)
    invoice.making_usd = sum((line.making_usd for line in lines), ZERO)
    invoice.total_value_usd = sum((line.total_value_usd for line in lines), ZERO)
    invoice.factory_cost_usd = sum((line.cost_usd for line in lines), ZERO)
    for line in lines:
        new_lot(
            db,
            unit="showroom",
            location_id=data.showroom_location_id,
            purity_id=line.purity_id,
            weight=line.weight,
            cost=line.total_value_usd,
            company_cost=line.company_cost_usd,
            factor=line.valuation_factor,
            invoice_id=invoice.id,
        )
    return {
        "id": invoice.id,
        "kind": "internal_invoice",
        "gold_24k": str(invoice.gold_24k),
        "making_usd": str(invoice.making_usd),
        "message": "Showroom supplied; register pieces on receipt",
    }


async def receive_showroom(db, invoice_id, data, user_id):
    invoice = await db.get(InternalInvoice, invoice_id)
    if invoice is None or invoice.tracking_mode != "weight" or invoice.reversal_of_id is not None:
        raise ValueError("Weight supply invoice not found")
    await lock_locations(db, invoice.showroom_location_id)
    invoice = await db.scalar(
        select(InternalInvoice).where(InternalInvoice.id == invoice_id).with_for_update()
    )
    if await db.scalar(
        select(InternalInvoice.id).where(InternalInvoice.reversal_of_id == invoice.id)
    ):
        raise ValueError("This supply invoice has been reversed")
    rows = list(
        await db.scalars(
            select(FactoryWeightLine).where(FactoryWeightLine.invoice_id == invoice.id)
        )
    )
    by_purity = {row.purity_id: row for row in rows}
    registered = list(
        await db.scalars(
            select(ProductionPiece).where(ProductionPiece.internal_invoice_id == invoice.id)
        )
    )
    remaining_making = {row.purity_id: row.making_usd for row in rows}
    remaining_charge = {row.purity_id: row.gold_24k for row in rows}
    for previous in registered:
        purity_id = previous.product.purity_id
        remaining_making[purity_id] -= previous.making_charge
        remaining_charge[purity_id] -= previous.gold_charge_24k
    pending_weights = dict(
        (
            await db.execute(
                select(FinishedGoldLot.purity_id, func.sum(FinishedGoldLot.remaining_weight))
                .where(FinishedGoldLot.invoice_id == invoice.id)
                .group_by(FinishedGoldLot.purity_id)
            )
        ).all()
    )
    ids = []
    for requested in data.pieces:
        product = await validate_purchase_product(db, requested.product_id, "item")
        trade = by_purity.get(product.purity_id)
        if trade is None:
            raise ValueError("The received product purity is not on this supply invoice")
        cost, company, _ = await consume(
            db,
            unit="showroom",
            location_id=invoice.showroom_location_id,
            purity_id=product.purity_id,
            weight=requested.weight,
            invoice_id=invoice.id,
        )
        last = requested.weight == pending_weights[product.purity_id]
        charge = (
            remaining_charge[product.purity_id]
            if last
            else min(
                grams24(requested.weight, trade.valuation_factor),
                remaining_charge[product.purity_id],
            )
        )
        making = (
            remaining_making[product.purity_id]
            if last
            else min(
                money(trade.making_usd * requested.weight / trade.weight),
                remaining_making[product.purity_id],
            )
        )
        remaining_charge[product.purity_id] -= charge
        remaining_making[product.purity_id] -= making
        pending_weights[product.purity_id] -= requested.weight
        piece = ProductionPiece(
            batch_id=None,
            internal_invoice_id=invoice.id,
            product_id=product.id,
            weight=requested.weight,
            valuation_factor=trade.valuation_factor,
            gold_charge_24k=charge,
            gold_price_per_gram=value4(invoice.gold_price_usd * trade.valuation_factor),
            making_charge=making,
            total_cost_usd=cost,
        )
        db.add(piece)
        await db.flush()
        item = await create_item(
            db,
            InventoryItemCreate(
                production_piece_id=piece.id,
                location_id=invoice.showroom_location_id,
                status="in_stock",
                image_url=requested.image_url,
            ),
        )
        item.owner_cost_usd, item.company_cost_usd = cost, company
        item.acquisition_internal_id = invoice.id
        await ops().attach_photo(db, requested.photo_token, item, user_id)
        db.add(
            InternalInvoiceLine(
                invoice_id=invoice.id,
                inventory_item_id=item.id,
                gold_24k=charge,
                making_usd=piece.making_charge,
                factory_cost_usd=company,
                showroom_cost_usd=cost,
            )
        )
        db.add(
            InventoryMovement(
                unit="showroom",
                inventory_item_id=item.id,
                movement_type="internal_receipt",
                to_location_id=invoice.showroom_location_id,
                created_by=user_id,
            )
        )
        ids.append(item.id)
    return {
        "id": invoice.id,
        "kind": "showroom_receipt",
        "inventory_item_ids": ids,
        "message": "Showroom pieces registered",
    }


async def reverse_supply(db, invoice, note, user_id):
    await lock_locations(db, invoice.factory_location_id, invoice.showroom_location_id)
    invoice = await db.scalar(
        select(InternalInvoice).where(InternalInvoice.id == invoice.id).with_for_update()
    )
    if invoice.reversal_of_id is not None or await db.scalar(
        select(InternalInvoice.id).where(InternalInvoice.reversal_of_id == invoice.id)
    ):
        raise ValueError("Supply invoice already reversed")
    lots = list(
        await db.scalars(
            select(FinishedGoldLot)
            .where(FinishedGoldLot.invoice_id == invoice.id)
            .with_for_update()
        )
    )
    if any(lot.remaining_weight != lot.weight for lot in lots):
        raise ValueError(
            "Some showroom pieces have already been registered; this supply cannot be reversed"
        )
    for lot in lots:
        lot.remaining_weight = lot.remaining_cost_usd = lot.remaining_company_cost_usd = ZERO
    lines = list(
        await db.scalars(
            select(FactoryWeightLine).where(FactoryWeightLine.invoice_id == invoice.id)
        )
    )
    for line in lines:
        await restore(db, line.allocations)
    reversal = InternalInvoice(
        tracking_mode="weight",
        factory_location_id=invoice.factory_location_id,
        showroom_location_id=invoice.showroom_location_id,
        gold_24k=-invoice.gold_24k,
        making_usd=-invoice.making_usd,
        gold_price_usd=invoice.gold_price_usd,
        total_value_usd=-invoice.total_value_usd,
        factory_cost_usd=-invoice.factory_cost_usd,
        note=note,
        reversal_of_id=invoice.id,
        created_by=user_id,
    )
    db.add(reversal)
    await db.flush()
    return {
        "id": reversal.id,
        "kind": "internal_invoice_reversal",
        "message": "Weight supply reversed",
    }


async def sale_detail(db, sale_id):
    # Scope through the owning Sale, since lines themselves are shared invoice records.
    sale = await db.get(Sale, sale_id)
    if sale is None:
        raise ValueError("Sale not found")
    rows = list(
        await db.scalars(select(FactoryWeightLine).where(FactoryWeightLine.sale_id == sale_id))
    )
    return [record(row) for row in rows]


async def pending_receipts(db):
    unit = active_unit()
    statement = select(FinishedGoldLot).where(
        FinishedGoldLot.unit == unit,
        FinishedGoldLot.invoice_id.is_not(None),
        FinishedGoldLot.remaining_weight > 0,
    )
    rows = list(
        await db.scalars(statement.order_by(FinishedGoldLot.invoice_id, FinishedGoldLot.id))
    )
    return [record(row) for row in rows]


async def reverse_seed(db, original, note, user_id):
    await lock_locations(db, original.location_id)
    if await db.scalar(
        select(OperationDocument.id).where(OperationDocument.reversal_of_id == original.id)
    ):
        raise ValueError("Finished gold balance already reversed")
    lots = list(
        await db.scalars(
            select(FinishedGoldLot)
            .where(FinishedGoldLot.operation_id == original.id)
            .with_for_update()
        )
    )
    if any(lot.remaining_weight != lot.weight for lot in lots):
        raise ValueError("Some finished gold from this balance has already been used")
    for lot in lots:
        lot.remaining_weight = lot.remaining_cost_usd = lot.remaining_company_cost_usd = ZERO
    doc = await ops().document(
        db,
        unit="factory",
        kind="reversal",
        location_id=original.location_id,
        user_id=user_id,
        note=note,
        reversal_of_id=original.id,
        details={"original_kind": "finished_opening"},
    )
    return {"id": doc.id, "kind": "reversal", "message": "Finished gold balance reversed"}
