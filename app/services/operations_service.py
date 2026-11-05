"""Atomic, auditable operations for independent Factory and Showroom accounts."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select, text

from app.core.workspace import in_workspace
from app.models import (
    CashEntry,
    GoldPurity,
    InventoryBalance,
    InventoryItem,
    InventoryMovement,
    PhotoUpload,
    Sale,
    SaleItem,
)
from app.models.operations import (
    InternalInvoice,
    InternalInvoiceLine,
    InternalPayment,
    OperationDocument,
    ProductionBatch,
    ProductionPiece,
)
from app.schemas.inventory import InventoryItemCreate
from app.services.gold_conversion import allocate_charge, grams24, purchase_factor
from app.services.gold_price import get_quote, price_per_gram, require_fresh_quote
from app.services.inventory_service import create_item
from app.services.product_inventory_type import validate_purchase_product
from app.services.supplier_ledger_service import post_entry
from app.services.transaction_validation import require_active_supplier
from app.services.workspace_stock import change_stock, lock_locations, value4

ZERO = Decimal(0)


def allocate_value(total, weights):
    units = int(value4(total) * 10000)
    raw = [Decimal(units) * weight / sum(weights) for weight in weights]
    whole = [int(value) for value in raw]
    order = sorted(range(len(raw)), key=lambda i: (-(raw[i] - whole[i]), i))
    for i in order[: units - sum(whole)]:
        whole[i] += 1
    return [Decimal(value) / 10000 for value in whole]


async def cash_available(db, unit, location_id):
    # Explicit unit condition is essential inside paired, unscoped operations.
    with in_workspace(None):
        return await db.scalar(
            select(func.coalesce(func.sum(CashEntry.amount_usd), 0)).where(
                CashEntry.unit == unit, CashEntry.location_id == location_id
            )
        )


async def require_cash(db, unit, location_id, amount):
    if amount > 0 and await cash_available(db, unit, location_id) < amount:
        raise ValueError(f"Insufficient cash in the {unit} drawer")


def cash_entry(db, doc, unit, location_id, amount, kind):
    if amount:
        db.add(
            CashEntry(
                unit=unit,
                location_id=location_id,
                amount_usd=amount,
                operation_id=doc.id,
                kind=kind,
                description=doc.note,
                created_by=doc.created_by,
                created_at=doc.created_at,
            )
        )


async def document(
    db,
    *,
    unit,
    kind,
    location_id,
    user_id,
    note,
    amount=ZERO,
    other_unit=None,
    other_location_id=None,
    details=None,
    reversal_of_id=None,
):
    doc = OperationDocument(
        unit=unit,
        kind=kind,
        location_id=location_id,
        created_by=user_id,
        note=note,
        amount_usd=amount,
        other_unit=other_unit,
        other_location_id=other_location_id,
        details=details or {},
        reversal_of_id=reversal_of_id,
    )
    db.add(doc)
    await db.flush()
    return doc


async def capital(db, data, user_id, unit, kind):
    await lock_locations(db, data.location_id)
    if kind != "adjustment" and (data.cash_usd < 0 or any(line.weight <= 0 for line in data.gold)):
        raise ValueError("Opening balances and additions must be nonnegative")
    if not data.cash_usd and not data.gold:
        raise ValueError("Enter cash or at least one bulk gold balance")
    if kind == "opening":
        if await db.scalar(
            select(OperationDocument.id).where(
                OperationDocument.unit == unit,
                OperationDocument.location_id == data.location_id,
                OperationDocument.kind == "opening",
            )
        ):
            raise ValueError("Opening balances already exist; record an addition or adjustment")
        if await cash_available(db, unit, data.location_id) != 0 or await db.scalar(
            select(InventoryBalance.id)
            .where(
                InventoryBalance.unit == unit,
                InventoryBalance.location_id == data.location_id,
                InventoryBalance.total_weight != 0,
            )
            .limit(1)
        ):
            raise ValueError("This workspace already has balances; use an addition or adjustment")
    await require_cash(db, unit, data.location_id, -data.cash_usd)
    seen, snapshots = set(), []
    for line in sorted(data.gold, key=lambda x: (x.purity_id, x.placement or unit)):
        placement = line.placement or unit
        key = (line.purity_id, placement)
        if key in seen or not line.weight:
            raise ValueError("Enter each purity and stock bucket once with a nonzero weight")
        seen.add(key)
        purity = await db.get(GoldPurity, line.purity_id)
        if purity is None:
            raise ValueError("Purity not found")
        if line.weight > 0 and line.value_usd is None:
            raise ValueError("Record the opening/additional gold value; zero is allowed explicitly")
        value = await change_stock(
            db,
            unit=unit,
            location_id=data.location_id,
            purity_id=line.purity_id,
            placement=placement,
            delta=line.weight,
            value=line.value_usd,
        )
        snapshots.append(
            {
                "purity_id": line.purity_id,
                "placement": placement,
                "weight": str(line.weight),
                "value_usd": str(value) if value is not None else None,
                "gold_24k": str(grams24(line.weight, purchase_factor(purity))),
            }
        )
    doc = await document(
        db,
        unit=unit,
        kind=kind,
        location_id=data.location_id,
        user_id=user_id,
        note=data.note,
        amount=data.cash_usd,
        details={"gold": snapshots},
    )
    if data.effective_at is not None:
        doc.created_at = data.effective_at
    cash_entry(
        db,
        doc,
        unit,
        data.location_id,
        data.cash_usd,
        "adjustment" if kind == "adjustment" else "capital",
    )
    return {"id": doc.id, "kind": kind, "message": "Balances recorded"}


async def value_stock(db, data, user_id, unit):
    await lock_locations(db, data.location_id)
    stock = await db.scalar(
        select(InventoryBalance)
        .where(
            InventoryBalance.unit == unit,
            InventoryBalance.location_id == data.location_id,
            InventoryBalance.purity_id == data.purity_id,
            InventoryBalance.placement == (data.placement or unit),
        )
        .with_for_update()
    )
    if stock is None or stock.total_weight <= 0:
        raise ValueError("Choose an existing nonempty bulk stock bucket")
    before = stock.cost_usd
    stock.cost_usd = data.value_usd
    doc = await document(
        db,
        unit=unit,
        kind="valuation",
        location_id=data.location_id,
        user_id=user_id,
        note=data.note,
        details={
            "purity_id": data.purity_id,
            "placement": stock.placement,
            "before_usd": str(before) if before is not None else None,
            "after_usd": str(data.value_usd),
            "weight": str(stock.total_weight),
        },
    )
    return {"id": doc.id, "kind": "valuation", "message": "Stock value recorded"}


async def transfer_cash(db, data, user_id, unit):
    if data.to_unit == unit:
        raise ValueError("Choose the other workspace")
    await lock_locations(db, data.location_id, data.to_location_id)
    await require_cash(db, unit, data.location_id, data.amount_usd)
    doc = await document(
        db,
        unit=unit,
        kind="cash_transfer",
        location_id=data.location_id,
        other_unit=data.to_unit,
        other_location_id=data.to_location_id,
        user_id=user_id,
        note=data.note,
        amount=data.amount_usd,
    )
    cash_entry(db, doc, unit, data.location_id, -data.amount_usd, "cash_transfer")
    cash_entry(db, doc, data.to_unit, data.to_location_id, data.amount_usd, "cash_transfer")
    return {"id": doc.id, "kind": "cash_transfer", "message": "Cash transferred"}


async def transfer_gold(db, data, user_id, unit):
    if data.to_unit == unit:
        raise ValueError("Choose the other workspace")
    await lock_locations(db, data.location_id, data.to_location_id)
    if await db.get(GoldPurity, data.purity_id) is None:
        raise ValueError("Purity not found")
    value = await change_stock(
        db,
        unit=unit,
        location_id=data.location_id,
        purity_id=data.purity_id,
        placement=data.placement or unit,
        delta=-data.weight,
    )
    await change_stock(
        db,
        unit=data.to_unit,
        location_id=data.to_location_id,
        purity_id=data.purity_id,
        placement=data.to_placement or data.to_unit,
        delta=data.weight,
        value=value,
    )
    doc = await document(
        db,
        unit=unit,
        kind="gold_transfer",
        location_id=data.location_id,
        other_unit=data.to_unit,
        other_location_id=data.to_location_id,
        user_id=user_id,
        note=data.note,
        details={
            "purity_id": data.purity_id,
            "weight": str(data.weight),
            "placement": data.placement or unit,
            "to_placement": data.to_placement or data.to_unit,
            "value_usd": str(value) if value is not None else None,
        },
    )
    return {"id": doc.id, "kind": "gold_transfer", "message": "Gold transferred"}


async def attach_photo(db, token, item, user_id):
    if not token:
        return
    upload = await db.scalar(
        select(PhotoUpload).where(PhotoUpload.token == token).with_for_update()
    )
    if (
        upload is None
        or upload.created_by != user_id
        or upload.inventory_item_id is not None
        or upload.expires_at <= datetime.now(UTC)
    ):
        raise ValueError("Photo is unavailable or expired")
    upload.inventory_item_id = item.id
    item.image_url = f"/api/v1/media/items/{upload.filename}"


async def production(db, data, user_id):
    await lock_locations(db, data.location_id)
    await require_cash(db, "factory", data.location_id, data.direct_cost_usd)
    purities = {
        id: await db.get(GoldPurity, id)
        for id in sorted({line.purity_id for line in data.inputs + data.scrap})
    }
    if any(value is None for value in purities.values()):
        raise ValueError("Purity not found")
    products = {
        id: await validate_purchase_product(db, id, "item")
        for id in sorted({line.product_id for line in data.pieces})
    }
    for product in products.values():
        if product.purity_id not in purities:
            purities[product.purity_id] = await db.get(GoldPurity, product.purity_id)
    input_gold = sum(
        (line.weight * purchase_factor(purities[line.purity_id]) for line in data.inputs), ZERO
    )
    output_weights = [
        line.weight * purchase_factor(purities[products[line.product_id].purity_id])
        for line in data.pieces
    ]
    output_gold = sum(output_weights, ZERO)
    scrap_weights = [line.weight * purchase_factor(purities[line.purity_id]) for line in data.scrap]
    scrap_gold = sum(scrap_weights, ZERO)
    if abs(input_gold - output_gold - scrap_gold - data.loss_gold_24k) > Decimal("0.001"):
        raise ValueError(
            "Gold must balance: inputs = finished pieces + scrap + declared loss (24K equivalent)"
        )
    if input_gold <= 0:
        raise ValueError("Production requires positive gold input")
    material, inputs = ZERO, []
    for line in sorted(data.inputs, key=lambda x: (x.purity_id, x.placement or "factory")):
        value = await change_stock(
            db,
            unit="factory",
            location_id=data.location_id,
            purity_id=line.purity_id,
            placement=line.placement or "factory",
            delta=-line.weight,
        )
        if value is None:
            raise ValueError("Record the bulk stock value before production")
        material += value
        inputs.append(
            {
                "purity_id": line.purity_id,
                "placement": line.placement or "factory",
                "weight": str(line.weight),
                "value_usd": str(value),
            }
        )
    scrap_values = [value4(material * weight / input_gold) for weight in scrap_weights]
    scrap = []
    for line, value in zip(data.scrap, scrap_values, strict=True):
        await change_stock(
            db,
            unit="factory",
            location_id=data.location_id,
            purity_id=line.purity_id,
            placement=line.placement or "factory",
            delta=line.weight,
            value=value,
        )
        scrap.append(
            {
                "purity_id": line.purity_id,
                "placement": line.placement or "factory",
                "weight": str(line.weight),
                "value_usd": str(value),
            }
        )
    finished_material = material - sum(scrap_values, ZERO)
    total = finished_material + data.direct_cost_usd
    costs = allocate_value(total, output_weights)
    direct_costs = allocate_value(data.direct_cost_usd, output_weights)
    charges = allocate_charge(grams24(output_gold, Decimal(1)), output_weights)
    quote = await get_quote()
    require_fresh_quote(quote)
    doc = await document(
        db,
        unit="factory",
        kind="production",
        location_id=data.location_id,
        user_id=user_id,
        note=data.note or data.reference or "Production batch",
        amount=data.direct_cost_usd,
    )
    batch = ProductionBatch(
        unit="factory",
        location_id=data.location_id,
        reference=data.reference,
        note=data.note,
        material_cost_usd=finished_material,
        direct_cost_usd=data.direct_cost_usd,
        total_cost_usd=total,
        input_gold_24k=input_gold,
        output_gold_24k=output_gold,
        scrap_gold_24k=scrap_gold,
        loss_gold_24k=data.loss_gold_24k,
        details={"inputs": inputs, "scrap": scrap},
        operation_id=doc.id,
        gold_quote_at=datetime.fromisoformat(quote["fetched_at"]),
        created_by=user_id,
    )
    db.add(batch)
    await db.flush()
    ids = []
    for index, line in enumerate(data.pieces):
        purity = purities[products[line.product_id].purity_id]
        piece = ProductionPiece(
            batch_id=batch.id,
            product_id=line.product_id,
            weight=line.weight,
            valuation_factor=purchase_factor(purity),
            gold_charge_24k=charges[index],
            gold_price_per_gram=price_per_gram(quote, purity),
            making_charge=direct_costs[index],
            total_cost_usd=costs[index],
        )
        db.add(piece)
        await db.flush()
        item = await create_item(
            db,
            InventoryItemCreate(
                production_piece_id=piece.id,
                location_id=data.location_id,
                status="in_stock",
                image_url=line.image_url,
            ),
        )
        item.owner_cost_usd = costs[index]
        item.company_cost_usd = costs[index]
        await attach_photo(db, line.photo_token, item, user_id)
        db.add(
            InventoryMovement(
                unit="factory",
                inventory_item_id=item.id,
                movement_type="production",
                to_location_id=data.location_id,
                created_by=user_id,
            )
        )
        ids.append(item.id)
    cash_entry(db, doc, "factory", data.location_id, -data.direct_cost_usd, "production_cost")
    return {
        "id": batch.id,
        "kind": "production",
        "inventory_item_ids": ids,
        "total_cost_usd": str(total),
        "message": "Production recorded",
    }


async def locked_factory_pieces(db, pieces, location_id):
    ids = [line.inventory_item_id for line in pieces]
    if len(ids) != len(set(ids)):
        raise ValueError("A piece may appear only once")
    rows = list(
        await db.scalars(
            select(InventoryItem)
            .where(InventoryItem.unit == "factory", InventoryItem.id.in_(ids))
            .order_by(InventoryItem.id)
            .with_for_update(of=InventoryItem)
        )
    )
    mapping = {item.id: item for item in rows}
    if len(rows) != len(ids) or any(
        item.status != "in_stock" or item.location_id != location_id for item in rows
    ):
        raise ValueError("Select available factory pieces at this location")
    return mapping


async def piece_gold_24k(db, item):
    origin = item.origin_line
    if origin.gold_charge_24k is not None:
        return origin.gold_charge_24k
    purity = await db.get(GoldPurity, origin.product.purity_id)
    return grams24(origin.weight, purchase_factor(purity))


async def internal_invoice(db, data, user_id):
    await lock_locations(db, data.location_id, data.showroom_location_id)
    await db.execute(text("SELECT pg_advisory_xact_lock(827416205)"))
    items = await locked_factory_pieces(db, data.pieces, data.location_id)
    charges = {id: await piece_gold_24k(db, item) for id, item in items.items()}
    gold = sum((charges[line.inventory_item_id] for line in data.pieces), ZERO)
    making = sum((line.making_usd for line in data.pieces), ZERO)
    costs = sum((item.cost_basis_usd for item in items.values()), ZERO)
    total = sum(
        (
            value4(charges[line.inventory_item_id] * data.gold_price_usd + line.making_usd)
            for line in data.pieces
        ),
        ZERO,
    )
    invoice = InternalInvoice(
        factory_location_id=data.location_id,
        showroom_location_id=data.showroom_location_id,
        gold_24k=gold,
        making_usd=making,
        gold_price_usd=data.gold_price_usd,
        total_value_usd=total,
        factory_cost_usd=costs,
        note=data.note,
        created_by=user_id,
    )
    db.add(invoice)
    await db.flush()
    for line in data.pieces:
        item = items[line.inventory_item_id]
        charge = charges[item.id]
        agreed = value4(charge * data.gold_price_usd + line.making_usd)
        db.add(
            InternalInvoiceLine(
                invoice_id=invoice.id,
                inventory_item_id=item.id,
                gold_24k=charge,
                making_usd=line.making_usd,
                factory_cost_usd=item.cost_basis_usd,
                showroom_cost_usd=agreed,
            )
        )
        for unit, movement in [("factory", "internal_sale"), ("showroom", "internal_receipt")]:
            db.add(
                InventoryMovement(
                    unit=unit,
                    inventory_item_id=item.id,
                    movement_type=movement,
                    from_location_id=data.location_id,
                    to_location_id=data.showroom_location_id,
                    created_by=user_id,
                )
            )
        item.unit = "showroom"
        item.location_id = data.showroom_location_id
        item.owner_cost_usd = agreed
        item.acquisition_internal_id = invoice.id
    return {
        "id": invoice.id,
        "kind": "internal_invoice",
        "gold_24k": str(gold),
        "making_usd": str(making),
        "total_value_usd": str(total),
        "message": "Showroom supplied",
    }


async def internal_balance(db):
    gold, usd = (
        await db.execute(
            select(
                func.coalesce(func.sum(InternalInvoice.gold_24k), 0),
                func.coalesce(func.sum(InternalInvoice.making_usd), 0),
            )
        )
    ).one()
    paid_gold, paid_usd = (
        await db.execute(
            select(
                func.coalesce(func.sum(InternalPayment.gold_24k), 0),
                func.coalesce(func.sum(InternalPayment.making_usd), 0),
            )
        )
    ).one()
    return {
        "gold_24k": gold - paid_gold,
        "making_usd": usd - paid_usd,
        "is_settled": gold == paid_gold and usd == paid_usd,
    }


async def internal_payment(db, data, user_id):
    await lock_locations(db, data.showroom_location_id, data.factory_location_id)
    await db.execute(text("SELECT pg_advisory_xact_lock(827416205)"))
    purity = await db.get(GoldPurity, data.purity_id) if data.purity_id else None
    if data.gold_grams and purity is None:
        raise ValueError("Purity not found")
    factor = purity.repayment_factor if purity else Decimal(1)
    credit = grams24(
        data.gold_grams * factor
        + (data.cash_gold_usd / data.gold_price_usd if data.cash_gold_usd else ZERO),
        Decimal(1),
    )
    if not credit and not data.making_usd:
        raise ValueError("Payment is below the recorded gold precision")
    sent = data.direction == "showroom_to_factory"
    sign = 1 if sent else -1
    balance = await internal_balance(db)
    if data.close_account and (
        balance["gold_24k"] - sign * credit != 0
        or balance["making_usd"] - sign * data.making_usd != 0
    ):
        raise ValueError("Full settlement requires zero gold and zero making-charge balances")
    source, destination = ("showroom", "factory") if sent else ("factory", "showroom")
    source_location = data.showroom_location_id if sent else data.factory_location_id
    dest_location = data.factory_location_id if sent else data.showroom_location_id
    source_placement = data.showroom_placement if sent else data.factory_placement
    dest_placement = data.factory_placement if sent else data.showroom_placement
    cash = data.making_usd + data.cash_gold_usd
    await require_cash(db, source, source_location, cash)
    value = None
    if data.gold_grams:
        value = await change_stock(
            db,
            unit=source,
            location_id=source_location,
            purity_id=data.purity_id,
            placement=source_placement,
            delta=-data.gold_grams,
        )
        await change_stock(
            db,
            unit=destination,
            location_id=dest_location,
            purity_id=data.purity_id,
            placement=dest_placement,
            delta=data.gold_grams,
            value=value,
        )
    doc = await document(
        db,
        unit=source,
        kind="internal_payment",
        location_id=source_location,
        other_unit=destination,
        other_location_id=dest_location,
        user_id=user_id,
        note=data.note,
        amount=cash,
        details={"source_placement": source_placement, "destination_placement": dest_placement},
    )
    payment = InternalPayment(
        operation_id=doc.id,
        direction=data.direction,
        gold_24k=sign * credit,
        making_usd=sign * data.making_usd,
        physical_purity_id=data.purity_id,
        physical_gold_grams=data.gold_grams,
        cash_gold_usd=data.cash_gold_usd,
        gold_price_usd=data.gold_price_usd,
        repayment_factor=factor,
        stock_value_usd=value,
        created_by=user_id,
    )
    db.add(payment)
    cash_entry(db, doc, source, source_location, -cash, "internal_payment")
    cash_entry(db, doc, destination, dest_location, cash, "internal_payment")
    await db.flush()
    return {"id": payment.id, "kind": "internal_payment", "message": "Internal payment recorded"}


async def supplier_item_sale(db, data, user_id):
    await lock_locations(db, data.location_id)
    await require_active_supplier(db, data.supplier_id, exclusive=True)
    items = await locked_factory_pieces(db, data.pieces, data.location_id)
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
        created_at=datetime.now(UTC),
        gold_quote_at=datetime.fromisoformat(quote["fetched_at"]),
    )
    db.add(sale)
    await db.flush()
    gold, making = ZERO, ZERO
    for line in data.pieces:
        item = items[line.inventory_item_id]
        origin = item.origin_line
        charge = await piece_gold_24k(db, item)
        purity = await db.get(GoldPurity, origin.product.purity_id)
        value = value4(charge * Decimal(quote["gram_24k_usd"]) + line.making_usd)
        db.add(
            SaleItem(
                unit="factory",
                sale_id=sale.id,
                inventory_item_id=item.id,
                gold_price_per_gram=price_per_gram(quote, purity),
                sell_price=value,
                discount=0,
                gold_24k=charge,
                making_usd=line.making_usd,
                cost_usd=item.cost_basis_usd,
                company_cost_usd=item.company_cost_usd
                if item.company_cost_usd is not None
                else item.cost_basis_usd,
            )
        )
        item.status = "sold"
        db.add(
            InventoryMovement(
                unit="factory",
                inventory_item_id=item.id,
                movement_type="supplier_sale",
                from_location_id=item.location_id,
                sale_id=sale.id,
                created_by=user_id,
            )
        )
        gold += charge
        making += line.making_usd
    from app.services.gold_conversion import canonical_purity

    canonical = await canonical_purity(db)
    await post_entry(
        db,
        supplier_id=data.supplier_id,
        purity_id=canonical.id,
        gold_grams=-gold,
        gold_24k=-gold,
        making_usd=-making,
        source_key=f"supplier-items:{sale.id}",
        kind="sale",
        created_by=user_id,
        sale_id=sale.id,
    )
    return {
        "id": sale.id,
        "kind": "supplier_item_sale",
        "gold_24k": str(gold),
        "making_usd": str(making),
        "message": "Supplier sale recorded",
    }


async def reverse_operation(db, operation_id, note, user_id, unit):
    original = await db.get(OperationDocument, operation_id)
    if original is None or unit not in {original.unit, original.other_unit}:
        raise ValueError("Operation not found in this workspace")
    if original.kind not in {
        "opening",
        "capital_in",
        "adjustment",
        "cash_transfer",
        "gold_transfer",
    }:
        raise ValueError("Use the dedicated production or internal-payment reversal")
    await lock_locations(
        db, original.location_id, original.other_location_id or original.location_id
    )
    if await db.scalar(
        select(OperationDocument.id).where(OperationDocument.reversal_of_id == original.id)
    ):
        raise ValueError("Operation already reversed")
    if original.kind in {"opening", "capital_in", "adjustment"}:
        await require_cash(db, original.unit, original.location_id, original.amount_usd)
        for line in original.details.get("gold", []):
            await change_stock(
                db,
                unit=original.unit,
                location_id=original.location_id,
                purity_id=line["purity_id"],
                placement=line["placement"],
                delta=-Decimal(line["weight"]),
                value=Decimal(line["value_usd"]) if line["value_usd"] is not None else None,
            )
        doc = await document(
            db,
            unit=original.unit,
            kind="reversal",
            location_id=original.location_id,
            user_id=user_id,
            note=note,
            amount=-original.amount_usd,
            reversal_of_id=original.id,
            details={"original_kind": original.kind},
        )
        cash_entry(db, doc, original.unit, original.location_id, -original.amount_usd, "adjustment")
    else:
        source, destination = original.other_unit, original.unit
        source_location, dest_location = original.other_location_id, original.location_id
        doc = await document(
            db,
            unit=source,
            kind="reversal",
            location_id=source_location,
            other_unit=destination,
            other_location_id=dest_location,
            user_id=user_id,
            note=note,
            amount=original.amount_usd,
            reversal_of_id=original.id,
            details={"original_kind": original.kind},
        )
        if original.kind == "cash_transfer":
            await require_cash(db, source, source_location, original.amount_usd)
            cash_entry(db, doc, source, source_location, -original.amount_usd, "cash_transfer")
            cash_entry(db, doc, destination, dest_location, original.amount_usd, "cash_transfer")
        else:
            line = original.details
            value = Decimal(line["value_usd"]) if line["value_usd"] is not None else None
            await change_stock(
                db,
                unit=source,
                location_id=source_location,
                purity_id=line["purity_id"],
                placement=line["to_placement"],
                delta=-Decimal(line["weight"]),
                value=value,
            )
            await change_stock(
                db,
                unit=destination,
                location_id=dest_location,
                purity_id=line["purity_id"],
                placement=line["placement"],
                delta=Decimal(line["weight"]),
                value=value,
            )
    return {"id": doc.id, "kind": "reversal", "message": "Operation reversed"}


async def reverse_production(db, batch_id, note, user_id):
    batch = await db.get(ProductionBatch, batch_id)
    if batch is None or batch.status != "active":
        raise ValueError("Choose an active factory production batch")
    await lock_locations(db, batch.location_id)
    batch = await db.scalar(
        select(ProductionBatch).where(ProductionBatch.id == batch_id).with_for_update()
    )
    if batch.status != "active":
        raise ValueError("Production batch already reversed")
    piece_ids = select(ProductionPiece.id).where(ProductionPiece.batch_id == batch.id)
    # Unscoped lookup is needed to detect pieces already supplied to the showroom.
    with in_workspace(None):
        items = list(
            await db.scalars(
                select(InventoryItem)
                .where(InventoryItem.production_piece_id.in_(piece_ids))
                .order_by(InventoryItem.id)
                .with_for_update(of=InventoryItem)
            )
        )
    if any(
        item.unit != "factory"
        or item.status != "in_stock"
        or item.location_id != batch.location_id
        or item.acquisition_internal_id is not None
        for item in items
    ):
        raise ValueError(
            "All batch pieces must still be available in the original factory location"
        )
    for line in batch.details["scrap"]:
        await change_stock(
            db,
            unit="factory",
            location_id=batch.location_id,
            purity_id=line["purity_id"],
            placement=line["placement"],
            delta=-Decimal(line["weight"]),
            value=Decimal(line["value_usd"]),
        )
    for line in batch.details["inputs"]:
        await change_stock(
            db,
            unit="factory",
            location_id=batch.location_id,
            purity_id=line["purity_id"],
            placement=line["placement"],
            delta=Decimal(line["weight"]),
            value=Decimal(line["value_usd"]),
        )
    doc = await document(
        db,
        unit="factory",
        kind="production_reversal",
        location_id=batch.location_id,
        user_id=user_id,
        note=note,
        amount=batch.direct_cost_usd,
        reversal_of_id=batch.operation_id,
    )
    cash_entry(db, doc, "factory", batch.location_id, batch.direct_cost_usd, "production_cost")
    for item in items:
        item.status = "voided"
        db.add(
            InventoryMovement(
                unit="factory",
                inventory_item_id=item.id,
                movement_type="production_reversal",
                from_location_id=item.location_id,
                created_by=user_id,
            )
        )
    batch.status = "reversed"
    return {"id": doc.id, "kind": "production_reversal", "message": "Production batch reversed"}


async def reverse_internal_invoice(db, invoice_id, note, user_id):
    original = await db.get(InternalInvoice, invoice_id)
    if original is None or original.reversal_of_id is not None:
        raise ValueError("Internal invoice not found")
    await lock_locations(db, original.factory_location_id, original.showroom_location_id)
    await db.execute(text("SELECT pg_advisory_xact_lock(827416205)"))
    if await db.scalar(
        select(InternalInvoice.id).where(InternalInvoice.reversal_of_id == original.id)
    ):
        raise ValueError("Internal invoice already reversed")
    lines = list(
        await db.scalars(
            select(InternalInvoiceLine).where(InternalInvoiceLine.invoice_id == original.id)
        )
    )
    ids = [line.inventory_item_id for line in lines]
    items = {
        item.id: item
        for item in await db.scalars(
            select(InventoryItem)
            .where(InventoryItem.id.in_(ids))
            .order_by(InventoryItem.id)
            .with_for_update(of=InventoryItem)
        )
    }
    if len(items) != len(ids) or any(
        item.unit != "showroom"
        or item.status != "in_stock"
        or item.acquisition_internal_id != original.id
        for item in items.values()
    ):
        raise ValueError("All supplied pieces must still be available in the showroom")
    if await db.scalar(select(SaleItem.id).where(SaleItem.inventory_item_id.in_(ids)).limit(1)):
        raise ValueError("Pieces with external sale history require a return workflow")
    reversal = InternalInvoice(
        factory_location_id=original.factory_location_id,
        showroom_location_id=original.showroom_location_id,
        gold_24k=-original.gold_24k,
        making_usd=-original.making_usd,
        gold_price_usd=original.gold_price_usd,
        total_value_usd=-original.total_value_usd,
        factory_cost_usd=-original.factory_cost_usd,
        note=note,
        reversal_of_id=original.id,
        created_by=user_id,
    )
    db.add(reversal)
    await db.flush()
    for line in lines:
        item = items[line.inventory_item_id]
        item.unit = "factory"
        item.location_id = original.factory_location_id
        item.owner_cost_usd = line.factory_cost_usd
        item.acquisition_internal_id = None
        db.add(
            InternalInvoiceLine(
                invoice_id=reversal.id,
                inventory_item_id=item.id,
                gold_24k=-line.gold_24k,
                making_usd=-line.making_usd,
                factory_cost_usd=-line.factory_cost_usd,
                showroom_cost_usd=-line.showroom_cost_usd,
            )
        )
        for unit in ["factory", "showroom"]:
            db.add(
                InventoryMovement(
                    unit=unit,
                    inventory_item_id=item.id,
                    movement_type="internal_reversal",
                    from_location_id=original.showroom_location_id,
                    to_location_id=original.factory_location_id,
                    created_by=user_id,
                )
            )
    return {"id": reversal.id, "kind": "internal_reversal", "message": "Internal invoice reversed"}


async def reverse_internal_payment(db, payment_id, note, user_id):
    original = await db.get(InternalPayment, payment_id)
    if original is None or original.reversal_of_id is not None:
        raise ValueError("Internal payment not found")
    source_doc = await db.get(OperationDocument, original.operation_id)
    await lock_locations(db, source_doc.location_id, source_doc.other_location_id)
    await db.execute(text("SELECT pg_advisory_xact_lock(827416205)"))
    if await db.scalar(
        select(InternalPayment.id).where(InternalPayment.reversal_of_id == original.id)
    ):
        raise ValueError("Internal payment already reversed")
    source, dest = source_doc.other_unit, source_doc.unit
    source_location, dest_location = source_doc.other_location_id, source_doc.location_id
    cash = abs(original.making_usd) + original.cash_gold_usd
    await require_cash(db, source, source_location, cash)
    if original.physical_gold_grams:
        await change_stock(
            db,
            unit=source,
            location_id=source_location,
            purity_id=original.physical_purity_id,
            placement=source_doc.details["destination_placement"],
            delta=-original.physical_gold_grams,
            value=original.stock_value_usd,
        )
        await change_stock(
            db,
            unit=dest,
            location_id=dest_location,
            purity_id=original.physical_purity_id,
            placement=source_doc.details["source_placement"],
            delta=original.physical_gold_grams,
            value=original.stock_value_usd,
        )
    doc = await document(
        db,
        unit=source,
        kind="internal_payment",
        location_id=source_location,
        other_unit=dest,
        other_location_id=dest_location,
        user_id=user_id,
        note=note,
        amount=cash,
        reversal_of_id=source_doc.id,
        details={
            "source_placement": source_doc.details["destination_placement"],
            "destination_placement": source_doc.details["source_placement"],
        },
    )
    payment = InternalPayment(
        operation_id=doc.id,
        direction="factory_to_showroom"
        if original.direction == "showroom_to_factory"
        else "showroom_to_factory",
        gold_24k=-original.gold_24k,
        making_usd=-original.making_usd,
        physical_purity_id=original.physical_purity_id,
        physical_gold_grams=original.physical_gold_grams,
        cash_gold_usd=original.cash_gold_usd,
        gold_price_usd=original.gold_price_usd,
        repayment_factor=original.repayment_factor,
        stock_value_usd=original.stock_value_usd,
        reversal_of_id=original.id,
        created_by=user_id,
    )
    db.add(payment)
    cash_entry(db, doc, source, source_location, -cash, "internal_payment")
    cash_entry(db, doc, dest, dest_location, cash, "internal_payment")
    await db.flush()
    return {
        "id": payment.id,
        "kind": "internal_payment_reversal",
        "message": "Internal payment reversed",
    }
