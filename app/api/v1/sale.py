from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import AdminUser, CashierUser
from app.core.database import get_db
from app.core.pagination import paginate
from app.models.sales import Sale
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
    current_user: CashierUser,
) -> SaleResponse:
    sale_data = sale_data.model_copy(
        update={"created_by": current_user.id, "created_at": datetime.now(UTC)}
    )
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
    current_user: AdminUser,
) -> SaleResponse:
    sale_data = sale_data.model_copy(
        update={"created_by": current_user.id, "created_at": datetime.now(UTC)}
    )
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
async def list_records(
    db: Annotated[AsyncSession, Depends(get_db)],
    response: Response,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    location_id: int | None = Query(None, gt=0),
    q: str | None = Query(None, min_length=1, max_length=50),
) -> list[SaleResponse]:
    statement = select(Sale)
    if location_id is not None:
        statement = statement.where(Sale.location_id == location_id)
    if q:
        statement = statement.where(Sale.invoice_number.icontains(q, autoescape=True))
    return await paginate(db, statement.order_by(Sale.id), response, limit, offset)


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
