from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import AdminUser
from app.core.database import get_db
from app.core.pagination import paginate
from app.models.product import Product
from app.schemas.products import (
    ProductCreate,
    ProductResponse,
    ProductUpdate,
)
from app.services.products_service import (
    create_product,
    get_product,
    update_product,
)

router = APIRouter(
    prefix="/products",
    tags=["Products"],
)


@router.post(
    "",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_product_endpoint(
    product_data: ProductCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: AdminUser,
) -> ProductResponse:

    try:
        product = await create_product(
            db,
            product_data,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return product


@router.get(
    "",
    response_model=list[ProductResponse],
)
async def list_records(
    db: Annotated[AsyncSession, Depends(get_db)],
    response: Response,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None, min_length=1, max_length=100),
) -> list[ProductResponse]:
    statement = select(Product).order_by(Product.id)
    if q:
        statement = statement.where(Product.name.icontains(q, autoescape=True))
    return await paginate(db, statement, response, limit, offset)


@router.get(
    "/{product_id}",
    response_model=ProductResponse,
)
async def get_product_endpoint(
    product_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProductResponse:

    product = await get_product(
        db,
        product_id,
    )

    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    return product


@router.patch(
    "/{product_id}",
    response_model=ProductResponse,
)
async def update_product_endpoint(
    product_id: int,
    product_data: ProductUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: AdminUser,
) -> ProductResponse:

    product = await get_product(
        db,
        product_id,
    )

    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    try:
        new_product = await update_product(
            db,
            product,
            product_data,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return new_product
