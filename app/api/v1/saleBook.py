from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.saleBook import (
    SaleBookUpdate,
    SaleBookCreate,
    SaleBookResponse,
)
from app.services.saleBook_service import (
    create_sale_book,
    update_sale_book,
    get_sale_book,
    get_sale_books,
)

router = APIRouter(
    prefix="/saleBook",
    tags=["SaleBook"],
)

@router.post(
    "",
    response_model=SaleBookResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_sale_book_endpoint(
    book_data: SaleBookCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SaleBookResponse:
    try:
        book = await create_sale_book(
            db,
            book_data,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )from exc
    return book

@router.get(
    "/{book_id}",
    response_model=SaleBookResponse,
)
async def get_sale_book_endpoint(
    book_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SaleBookResponse:
    book = await get_sale_book(
        db,
        book_id,
    )
    if book is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="book not found",
        )
    return book

@router.get(
    "",
    response_model=list[SaleBookResponse],
)
async def get_sale_books_endpoint(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[SaleBookResponse]:
    return await get_sale_books(db)

@router.patch(
    "/{book_id}",
    response_model=SaleBookResponse,
)
async def update_sale_book_endpoint(
    book_id: int,
    book_data: SaleBookUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SaleBookResponse:
    book = await get_sale_book(
        db,
        book_id,
    )
    if book is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="book not found",
        )
    try:
        new_book = await update_sale_book(
            db,
            book,
            book_data,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )from exc
    return new_book