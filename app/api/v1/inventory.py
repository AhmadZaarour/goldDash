from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import EmployeeUser
from app.core.database import get_db
from app.core.pagination import paginate
from app.models import InventoryMovement, InventoryStock, Product, PurchaseItem
from app.models.inventoryItem import InventoryItem
from app.schemas.inventory import (
    InventoryItemImageUpdate,
    InventoryItemResponse,
    InventoryMovementResponse,
    InventoryStockResponse,
)
from app.services.inventory_service import (
    get_item,
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
    response: Response,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None, min_length=1, max_length=100),
    barcode: str | None = None,
    purchase_id: int | None = Query(default=None, gt=0),
    item_status: Literal["in_stock", "sold"] | None = Query(default=None, alias="status"),
    location_id: int | None = Query(default=None, gt=0),
    purity_id: int | None = Query(default=None, gt=0),
    category_id: int | None = Query(default=None, gt=0),
    sort: Literal["id", "-id"] = "id",
) -> list[InventoryItemResponse]:
    statement = select(InventoryItem).join(PurchaseItem).join(Product)
    if q:
        statement = statement.where(
            or_(
                InventoryItem.barcode.icontains(q, autoescape=True),
                Product.name.icontains(q, autoescape=True),
                Product.sku.icontains(q, autoescape=True),
            )
        )
    for column, value in [
        (PurchaseItem.purchase_id, purchase_id),
        (InventoryItem.barcode, barcode),
        (InventoryItem.status, item_status),
        (InventoryItem.location_id, location_id),
        (Product.purity_id, purity_id),
        (Product.category_id, category_id),
    ]:
        if value is not None:
            statement = statement.where(column == value)
    statement = statement.order_by(InventoryItem.id.desc() if sort == "-id" else InventoryItem.id)
    return await paginate(db, statement, response, limit, offset)


@router.get(
    "/movements",
    response_model=list[InventoryMovementResponse],
)
async def get_all_movements_endpoint(
    db: Annotated[AsyncSession, Depends(get_db)],
    response: Response,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    inventory_item_id: int | None = Query(None, gt=0),
) -> list[InventoryMovementResponse]:
    statement = select(InventoryMovement)
    if inventory_item_id is not None:
        statement = statement.where(InventoryMovement.inventory_item_id == inventory_item_id)
    return await paginate(db, statement.order_by(InventoryMovement.id), response, limit, offset)


@router.get(
    "/stocks",
    response_model=list[InventoryStockResponse],
)
async def get_all_stock_endpoint(
    db: Annotated[AsyncSession, Depends(get_db)],
    response: Response,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    purchase_stock_id: int | None = Query(None, gt=0),
) -> list[InventoryStockResponse]:
    statement = select(InventoryStock)
    if purchase_stock_id is not None:
        statement = statement.where(InventoryStock.purchase_stock_id == purchase_stock_id)
    return await paginate(db, statement.order_by(InventoryStock.id), response, limit, offset)


@router.patch("/items/{item_id}/image", response_model=InventoryItemResponse)
async def update_item_image(
    item_id: int,
    data: InventoryItemImageUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: EmployeeUser,
) -> InventoryItemResponse:
    item = await db.get(InventoryItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    item.image_url = str(data.image_url) if data.image_url is not None else None
    await db.commit()
    await db.refresh(item)
    return item


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
