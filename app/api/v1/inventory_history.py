from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import AwareDatetime
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.pagination import paginate
from app.models.inventoryMovement import InventoryMovement
from app.models.itemReturn import ItemReturn
from app.models.saleItem import SaleItem
from app.models.stockTransfer import StockTransferRecord
from app.schemas.inventory_history import (
    ItemReturnResponse,
    ItemTransferResponse,
    StockTransferHistoryResponse,
)

router = APIRouter(
    prefix="/inventory", tags=["Inventory history"], dependencies=[Depends(get_current_user)]
)
Database = Annotated[AsyncSession, Depends(get_db)]


def filter_period(statement, column, from_at, to_at):
    if from_at and to_at and from_at >= to_at:
        raise HTTPException(422, "from_at must be before to_at")
    if from_at is not None:
        statement = statement.where(column >= from_at)
    if to_at is not None:
        statement = statement.where(column < to_at)
    return statement


def return_response(record, sale_line):
    return ItemReturnResponse(
        id=record.id,
        sale_item_id=record.sale_item_id,
        sale_id=sale_line.sale_id,
        inventory_item_id=sale_line.inventory_item_id,
        location_id=record.location_id,
        refund_usd=record.refund_usd,
        created_by=record.created_by,
        created_at=record.created_at,
    )


@router.get("/returns", response_model=list[ItemReturnResponse])
async def list_returns(
    db: Database,
    response: Response,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    location_id: int | None = Query(None, gt=0),
    sale_id: int | None = Query(None, gt=0),
    sale_item_id: int | None = Query(None, gt=0),
    inventory_item_id: int | None = Query(None, gt=0),
    created_by: int | None = Query(None, gt=0),
    from_at: AwareDatetime | None = None,
    to_at: AwareDatetime | None = None,
):
    statement = select(ItemReturn).join(SaleItem)
    for column, value in [
        (ItemReturn.location_id, location_id),
        (SaleItem.sale_id, sale_id),
        (ItemReturn.sale_item_id, sale_item_id),
        (SaleItem.inventory_item_id, inventory_item_id),
        (ItemReturn.created_by, created_by),
    ]:
        if value is not None:
            statement = statement.where(column == value)
    statement = filter_period(statement, ItemReturn.created_at, from_at, to_at)
    records = await paginate(db, statement.order_by(ItemReturn.id), response, limit, offset)
    if not records:
        return []
    lines = await db.scalars(
        select(SaleItem).where(SaleItem.id.in_([record.sale_item_id for record in records]))
    )
    lines_by_id = {line.id: line for line in lines}
    return [return_response(record, lines_by_id[record.sale_item_id]) for record in records]


@router.get("/returns/{return_id}", response_model=ItemReturnResponse)
async def get_return(return_id: int, db: Database):
    record = await db.get(ItemReturn, return_id)
    if record is None:
        raise HTTPException(404, "Return not found")
    line = await db.get(SaleItem, record.sale_item_id)
    return return_response(record, line)


@router.get("/transfers/items", response_model=list[ItemTransferResponse])
async def list_item_transfers(
    db: Database,
    response: Response,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    inventory_item_id: int | None = Query(None, gt=0),
    location_id: int | None = Query(None, gt=0),
    from_location_id: int | None = Query(None, gt=0),
    to_location_id: int | None = Query(None, gt=0),
    created_by: int | None = Query(None, gt=0),
    from_at: AwareDatetime | None = None,
    to_at: AwareDatetime | None = None,
):
    statement = select(InventoryMovement).where(InventoryMovement.movement_type == "transfer")
    for column, value in [
        (InventoryMovement.inventory_item_id, inventory_item_id),
        (InventoryMovement.from_location_id, from_location_id),
        (InventoryMovement.to_location_id, to_location_id),
        (InventoryMovement.created_by, created_by),
    ]:
        if value is not None:
            statement = statement.where(column == value)
    if location_id is not None:
        statement = statement.where(
            or_(
                InventoryMovement.from_location_id == location_id,
                InventoryMovement.to_location_id == location_id,
            )
        )
    statement = filter_period(statement, InventoryMovement.created_at, from_at, to_at)
    return await paginate(db, statement.order_by(InventoryMovement.id), response, limit, offset)


@router.get("/transfers/items/{transfer_id}", response_model=ItemTransferResponse)
async def get_item_transfer(transfer_id: int, db: Database):
    record = await db.scalar(
        select(InventoryMovement).where(
            InventoryMovement.id == transfer_id, InventoryMovement.movement_type == "transfer"
        )
    )
    if record is None:
        raise HTTPException(404, "Item transfer not found")
    return record


@router.get("/transfers/stocks", response_model=list[StockTransferHistoryResponse])
async def list_stock_transfers(
    db: Database,
    response: Response,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    purity_id: int | None = Query(None, gt=0),
    location_id: int | None = Query(None, gt=0),
    source_location_id: int | None = Query(None, gt=0),
    destination_location_id: int | None = Query(None, gt=0),
    source_placement: Literal["factory", "showroom"] | None = None,
    destination_placement: Literal["factory", "showroom"] | None = None,
    created_by: int | None = Query(None, gt=0),
    from_at: AwareDatetime | None = None,
    to_at: AwareDatetime | None = None,
):
    statement = select(StockTransferRecord)
    for column, value in [
        (StockTransferRecord.purity_id, purity_id),
        (StockTransferRecord.source_location_id, source_location_id),
        (StockTransferRecord.destination_location_id, destination_location_id),
        (StockTransferRecord.source_placement, source_placement),
        (StockTransferRecord.destination_placement, destination_placement),
        (StockTransferRecord.created_by, created_by),
    ]:
        if value is not None:
            statement = statement.where(column == value)
    if location_id is not None:
        statement = statement.where(
            or_(
                StockTransferRecord.source_location_id == location_id,
                StockTransferRecord.destination_location_id == location_id,
            )
        )
    statement = filter_period(statement, StockTransferRecord.created_at, from_at, to_at)
    return await paginate(db, statement.order_by(StockTransferRecord.id), response, limit, offset)


@router.get("/transfers/stocks/{transfer_id}", response_model=StockTransferHistoryResponse)
async def get_stock_transfer(transfer_id: int, db: Database):
    record = await db.get(StockTransferRecord, transfer_id)
    if record is None:
        raise HTTPException(404, "Stock transfer not found")
    return record
