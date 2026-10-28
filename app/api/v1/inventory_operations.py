from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import CashierUser, EmployeeUser
from app.core.database import get_db
from app.models import (
    GoldPurity,
    InventoryBalance,
    InventoryItem,
    InventoryMovement,
    Location,
    SaleItem,
)
from app.models.cashLedger import CashEntry
from app.models.itemReturn import ItemReturn

router = APIRouter(prefix="/inventory", tags=["Inventory operations"])
Database = Annotated[AsyncSession, Depends(get_db)]


class ItemTransfer(BaseModel):
    location_id: int


class ItemReturnCreate(BaseModel):
    sale_item_id: int
    location_id: int
    refund_usd: Decimal = Field(ge=0, max_digits=14, decimal_places=2)


class StockTransfer(BaseModel):
    purity_id: int
    source_location_id: int
    source_placement: Literal["factory", "showroom"]
    destination_location_id: int
    destination_placement: Literal["factory", "showroom"]
    weight: Decimal = Field(gt=0, max_digits=12, decimal_places=3)


async def active_location(db, location_id):
    location = await db.get(Location, location_id)
    if location is None or not location.is_active:
        raise HTTPException(404, "Active location not found")


@router.post("/items/{item_id}/transfer")
async def transfer_item(item_id: int, data: ItemTransfer, db: Database, user: EmployeeUser):
    await active_location(db, data.location_id)
    item = await db.scalar(
        select(InventoryItem).where(InventoryItem.id == item_id).with_for_update(of=InventoryItem)
    )
    if item is None:
        raise HTTPException(404, "Item not found")
    if item.status != "in_stock" or item.location_id == data.location_id:
        raise HTTPException(409, "Item must be available at a different location")
    db.add(
        InventoryMovement(
            inventory_item_id=item.id,
            movement_type="transfer",
            from_location_id=item.location_id,
            to_location_id=data.location_id,
            created_by=user.id,
        )
    )
    item.location_id = data.location_id
    await db.commit()
    return {"id": item.id, "location_id": item.location_id, "status": item.status}


@router.post("/returns", status_code=201)
async def return_item(data: ItemReturnCreate, db: Database, user: CashierUser):
    await active_location(db, data.location_id)
    line = await db.get(SaleItem, data.sale_item_id)
    if line is None:
        raise HTTPException(404, "Sale line not found")
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


class StockTransferResponse(BaseModel):
    id: int
    source_weight: Decimal
    destination_weight: Decimal


@router.post("/stocks/transfer", response_model=StockTransferResponse)
async def transfer_stock(data: StockTransfer, db: Database, user: EmployeeUser):
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
    await db.commit()
    return {
        "id": record.id,
        "source_weight": balances[source].total_weight,
        "destination_weight": balances[destination].total_weight,
    }
