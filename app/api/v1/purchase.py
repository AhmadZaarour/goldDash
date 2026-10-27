from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentUser
from app.schemas.purchases import (
    PurchaseCreate,
    PurchaseItemResponse,
    PurchaseResponse,
    PurchaseStockCreate,
    PurchaseStockResponse,
)
from app.services.purchase_service import (
    create_item_purchase,
    create_stock_purchase,
    get_purchase,
    get_purchase_items,
    get_purchase_stock,
    get_purchases,
)

router = APIRouter(
    prefix="/purchases",
    tags=["Purchases"],
)


@router.post(
    "/item",
    response_model=PurchaseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_items_purchase_endpoint(
    purchase_data: PurchaseCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
) -> PurchaseResponse:

    purchase_data = purchase_data.model_copy(update={"created_by": current_user.id})
    try:
        purchase = await create_item_purchase(
            db,
            purchase_data,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return purchase


@router.post(
    "/stock",
    response_model=PurchaseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_stock_purchase_endpoint(
    purchase_data: PurchaseStockCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
) -> PurchaseResponse:
    purchase_data = purchase_data.model_copy(update={"created_by": current_user.id})
    try:
        purchase = await create_stock_purchase(
            db,
            purchase_data,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return purchase


@router.get(
    "/{purchase_id}",
    response_model=PurchaseResponse,
)
async def get_purchase_endpoint(
    purchase_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PurchaseResponse:
    purchase = await get_purchase(
        db,
        purchase_id,
    )
    if purchase is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="purchase not found",
        )
    return purchase


@router.get(
    "",
    response_model=list[PurchaseResponse],
)
async def get_purchases_endpoint(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[PurchaseResponse]:
    return await get_purchases(db)


@router.get(
    "/items/{purchase_id}",
    response_model=list[PurchaseItemResponse],
)
async def get_purchase_items_endpoint(
    purchase_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[PurchaseItemResponse]:

    return await get_purchase_items(db, purchase_id)


@router.get(
    "/stock/{purchase_id}",
    response_model=PurchaseStockResponse,
)
async def get_purchase_stock_endpoint(
    purchase_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PurchaseStockResponse:
    purchase = await get_purchase_stock(
        db,
        purchase_id,
    )
    if purchase is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="purchase not found",
        )
    return purchase
