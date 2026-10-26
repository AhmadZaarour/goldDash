from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.categories import CategoryCreate, CategoryResponse, CategoryUpdate
from app.services.categories_service import (
    create_category,
    get_category,
    update_category,
)

router = APIRouter(
    prefix="/categories",
    tags=["Categories"],
)

@router.post(
    "",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_category_endpoint(
    category_data: CategoryCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CategoryResponse:

    try:
        category = await create_category(
            db,
            category_data,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return category

@router.get(
    "/{category_id}",
    response_model=CategoryResponse,
)
async def get_category_endpoint(
    category_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CategoryResponse:

    category = await get_category(db, category_id)

    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )

    return category

@router.patch(
    "/{category_id}",
    response_model=CategoryResponse,
)

async def update_categpry_endpoint(
    category_id: int,
    category_data: CategoryUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CategoryResponse:

    category = await get_category(
        db,
        category_id,
    )

    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )
    try:
        new_category = await update_category(
            db,
            category,
            category_data,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return new_category
