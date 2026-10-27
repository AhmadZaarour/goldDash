from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import CurrentUser
from app.schemas.sales import (
    SaleCreate,
    SaleItemResponse,
    SaleResponse,
    SaleStockCreate,
    SaleStockResponse,
)
from app.services.sale_service import (
    create_item_sale,
    create_stock_sale,
    get_sale,
    get_sale_items,
    get_sales,
    get_stock_sale,
)

router = APIRouter(
    prefix="/sales",
    tags=["Sales"],
)


@router.post(
    "/item",
    response_model=SaleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_sale_endpoint(
    sale_data: SaleCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
) -> SaleResponse:
    sale_data = sale_data.model_copy(update={"created_by": current_user.id})
    try:
        sale = await create_item_sale(
            db,
            sale_data,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return sale


@router.post(
    "/stock",
    response_model=SaleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_stock_sale_endpoint(
    sale_data: SaleStockCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: CurrentUser,
) -> SaleResponse:
    sale_data = sale_data.model_copy(update={"created_by": current_user.id})
    try:
        sale = await create_stock_sale(
            db,
            sale_data,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return sale


@router.get(
    "/{sale_id}",
    response_model=SaleResponse,
)
async def get_sale_endpoint(
    sale_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SaleResponse:
    sale = await get_sale(
        db,
        sale_id,
    )
    if sale is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="sale not found",
        )
    return sale


@router.get(
    "",
    response_model=list[SaleResponse],
)
async def get_sales_endpoint(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[SaleResponse]:
    return await get_sales(db)


@router.get(
    "/item/{sale_id}",
    response_model=list[SaleItemResponse],
)
async def get_sale_items_endpoint(
    sale_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[SaleItemResponse]:
    return await get_sale_items(
        db,
        sale_id,
    )


@router.get(
    "/stock/{sale_id}",
    response_model=SaleStockResponse,
)
async def get_sale_stock_endpoint(
    sale_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SaleStockResponse:
    sale = await get_stock_sale(
        db,
        sale_id,
    )
    if sale is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="sale not found",
        )
    return sale
