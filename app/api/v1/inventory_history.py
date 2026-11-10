from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import AwareDatetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.schemas.inventory_history import (
    ItemReturnResponse,
    ItemTransferResponse,
    StockTransferHistoryResponse,
)
from app.services.inventory_history_service import (
    list_returns_service,
    get_return_service,
    list_item_transfers_service,
    get_item_transfer_service,
    list_stock_transfers_service,
    get_stock_transfer_service,
)

router = APIRouter(
    prefix="/inventory", tags=["Inventory history"], dependencies=[Depends(get_current_user)]
)
Database = Annotated[AsyncSession, Depends(get_db)]

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
) -> list[ItemReturnResponse]:
    return await list_returns_service(
        db,
        response,
        limit,
        offset,
        location_id,
        sale_id,
        sale_item_id,
        inventory_item_id,
        created_by,
        from_at,
        to_at,
    )

@router.get("/returns/{return_id}", response_model=ItemReturnResponse)
async def get_return(return_id: int, db: Database):
    return await get_return_service(return_id, db)


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
    return await list_item_transfers_service(
        db,
        response,
        limit,
        offset,
        inventory_item_id,
        location_id,
        from_location_id,
        to_location_id,
        created_by,
        from_at,
        to_at,
    )

@router.get("/transfers/items/{transfer_id}", response_model=ItemTransferResponse)
async def get_item_transfer(transfer_id: int, db: Database):
    return await get_item_transfer_service(transfer_id, db)


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
    return await list_stock_transfers_service(
        db,
        response,
        limit,
        offset,
        purity_id,
        location_id,
        source_location_id,
        destination_location_id,
        source_placement,
        destination_placement,
        created_by,
        from_at,
        to_at,
    )

@router.get("/transfers/stocks/{transfer_id}", response_model=StockTransferHistoryResponse)
async def get_stock_transfer(transfer_id: int, db: Database) -> StockTransferHistoryResponse:
    return await get_stock_transfer_service(transfer_id, db)
