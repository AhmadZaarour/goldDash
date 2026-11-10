from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import CashierUser, EmployeeUser
from app.core.workspace import active_unit
from app.models import (
    GoldPurity,
    InventoryBalance,
    InventoryItem,
    InventoryMovement,
    SaleItem,
)
from app.models.cashLedger import CashEntry
from app.models.itemReturn import ItemReturn
from app.services.idempotency import IdempotencyKey, claim_operation, complete_operation
from app.services.transaction_validation import require_active_location
from app.schemas.inventory_operations import (
    ItemReturnCreate,
    ItemTransfer,
    StockTransfer,
    StockTransferResponse,
)

async def active_location(db, location_id):
    try:
        await require_active_location(db, location_id)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error

async def transfer_item_service(item_id: int, data: ItemTransfer, db: AsyncSession, user: EmployeeUser) -> dict[str, int | str]:
    await active_location(db, data.location_id)
    item = await db.scalar(
        select(InventoryItem).where(InventoryItem.id == item_id).with_for_update(of=InventoryItem)
    )
    if item is None:
        raise HTTPException(404, "Item not found")
    await active_location(db, item.location_id)
    if item.status != "in_stock" or item.location_id == data.location_id:
        raise HTTPException(409, "Item must be available at a different location")
    movement = InventoryMovement(
        inventory_item_id=item.id,
        movement_type="transfer",
        from_location_id=item.location_id,
        to_location_id=data.location_id,
        created_by=user.id,
    )
    db.add(movement)
    item.location_id = data.location_id
    await db.commit()
    return {
        "id": item.id,
        "transfer_id": movement.id,
        "location_id": item.location_id,
        "status": item.status,
    }

async def return_item_service(data: ItemReturnCreate, db: AsyncSession, user: CashierUser) -> dict[str, int | str | Decimal]:
    await active_location(db, data.location_id)
    line = await db.get(SaleItem, data.sale_item_id)
    if line is None:
        raise HTTPException(404, "Sale line not found")
    from app.models.sales import Sale

    sale = await db.get(Sale, line.sale_id)
    if sale is None or sale.kind != "customer":
        raise HTTPException(409, "Supplier sales require a supplier return document")
    item = await db.scalar(
        select(InventoryItem)
        .where(InventoryItem.id == line.inventory_item_id)
        .with_for_update(of=InventoryItem)
    )
    existing = await db.scalar(select(ItemReturn.id).where(ItemReturn.sale_item_id == line.id))
    if existing or item.status != "sold":
        raise HTTPException(409, "Sale line already returned or item is not sold")
    if data.refund_usd > Decimal(str(line.sell_price)):
        raise HTTPException(409, "Refund exceeds the recorded sale price")
    record = ItemReturn(
        sale_item_id=line.id,
        location_id=data.location_id,
        refund_usd=data.refund_usd,
        created_by=user.id,
    )
    db.add(record)
    db.add(
        InventoryMovement(
            inventory_item_id=item.id,
            movement_type="return",
            from_location_id=item.location_id,
            to_location_id=data.location_id,
            created_by=user.id,
            sale_id=line.sale_id,
        )
    )
    await db.flush()
    db.add(
        CashEntry(
            return_id=record.id,
            location_id=data.location_id,
            kind="refund",
            amount_usd=-data.refund_usd,
            created_by=user.id,
        )
    )
    item.status = "in_stock"
    item.location_id = data.location_id
    await db.commit()
    return {"id": record.id, "inventory_item_id": item.id, "status": item.status}

async def transfer_stock_service(
    data: StockTransfer, db: AsyncSession, user: EmployeeUser, idempotency_key: IdempotencyKey
) -> StockTransferResponse:
    receipt, replayed = await claim_operation(db, user.id, "stock:transfer", idempotency_key, data)
    if replayed:
        return StockTransferResponse.model_validate(receipt.response_data)
    if await db.get(GoldPurity, data.purity_id) is None:
        raise HTTPException(404, "Purity not found")
    source = (data.source_location_id, data.source_placement)
    destination = (data.destination_location_id, data.destination_placement)
    if source == destination:
        raise HTTPException(409, "Source and destination must differ")
    await active_location(db, source[0])
    await active_location(db, destination[0])
    # Create both buckets, then acquire locks in a consistent order for opposing transfers.
    for location_id, placement in sorted([source, destination]):
        await db.execute(
            insert(InventoryBalance)
            .values(
                unit=active_unit(),
                purity_id=data.purity_id,
                location_id=location_id,
                placement=placement,
                total_weight=0,
            )
            .on_conflict_do_nothing(constraint="uq_balance_bucket")
        )
    buckets = list(
        await db.scalars(
            select(InventoryBalance)
            .where(
                InventoryBalance.purity_id == data.purity_id,
                InventoryBalance.location_id.in_([source[0], destination[0]]),
            )
            .order_by(InventoryBalance.location_id, InventoryBalance.placement)
            .with_for_update()
        )
    )
    balances = {(b.location_id, b.placement): b for b in buckets}
    if balances[source].total_weight < data.weight:
        raise HTTPException(409, "Insufficient stock for transfer")
    value = (
        (balances[source].cost_usd * data.weight / balances[source].total_weight).quantize(
            Decimal("0.0001")
        )
        if balances[source].cost_usd is not None
        else None
    )
    if balances[source].cost_usd is not None:
        balances[source].cost_usd -= value
    if value is None or (
        balances[destination].total_weight > 0 and balances[destination].cost_usd is None
    ):
        balances[destination].cost_usd = None
    else:
        balances[destination].cost_usd = (balances[destination].cost_usd or Decimal(0)) + value
    balances[source].total_weight -= data.weight
    balances[destination].total_weight += data.weight
    # The audit record and both balance changes commit together.
    from app.models.stockTransfer import StockTransferRecord

    record = StockTransferRecord(
        purity_id=data.purity_id,
        source_location_id=source[0],
        source_placement=source[1],
        destination_location_id=destination[0],
        destination_placement=destination[1],
        weight=data.weight,
        created_by=user.id,
    )
    db.add(record)
    await db.flush()
    result = StockTransferResponse(
        id=record.id,
        source_weight=balances[source].total_weight,
        destination_weight=balances[destination].total_weight,
    )
    await complete_operation(db, receipt, result)
    return result