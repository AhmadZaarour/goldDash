from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.inventory import (
    InventoryItemResponse,
    InventoryMovementResponse,
    InventoryStockResponse,
)
from app.services.inventory_service import (
    get_all_movements,
    get_all_stock,
    get_item,
    get_items,
    get_movement,
    get_stock,
)

router = APIRouter(
    prefix="/inventory",
    tags=["Inventory"],
)


@router.get(
    "/items/{item_id}",
    response_model=InventoryItemResponse,
)
async def get_inventory_item_endpoint(
    item_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InventoryItemResponse:
    item = await get_item(
        db,
        item_id,
    )
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="item not found",
        )
    return item


@router.get(
    "/stocks/{stock_id}",
    response_model=InventoryStockResponse,
)
async def get_stock_endpoint(
    stock_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InventoryStockResponse:
    stock = await get_stock(
        db,
        stock_id,
    )
    if stock is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="stock does not exist",
        )
    return stock


@router.get(
    "/movements/{movement_id}",
    response_model=InventoryMovementResponse,
)
async def get_movement_endpoint(
    movement_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InventoryMovementResponse:
    movement = await get_movement(
        db,
        movement_id,
    )

    if movement is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no movement found",
        )
    return movement


@router.get(
    "/items",
    response_model=list[InventoryItemResponse],
)
async def get_all_items_endpoint(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[InventoryItemResponse]:
    return await get_items(db)


@router.get(
    "/movements",
    response_model=list[InventoryMovementResponse],
)
async def get_all_movements_endpoint(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[InventoryMovementResponse]:
    return await get_all_movements(db)


@router.get(
    "/stocks",
    response_model=list[InventoryStockResponse],
)
async def get_all_stock_endpoint(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[InventoryStockResponse]:
    return await get_all_stock(db)


# Compatibility aliases for the original item-only routes.
router.add_api_route(
    "",
    get_all_items_endpoint,
    methods=["GET"],
    response_model=list[InventoryItemResponse],
    include_in_schema=False,
)
router.add_api_route(
    "/{item_id}",
    get_inventory_item_endpoint,
    methods=["GET"],
    response_model=InventoryItemResponse,
    include_in_schema=False,
)
