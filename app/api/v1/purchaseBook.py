from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.purchaseBook import (
    PurchaseBookUpdate,
    PurchaseBookCreate,
    PurchaseBookResponse,
)
from app.services.purchaseBook_service import (
    create_purchase_book,
    update_purchase_book,
    get_purchase_book,
    get_purchase_books,
)

router = APIRouter(
    prefix="/purchaseBook",
    tags=["PurchaseBook"],
)

@router.post(
    "",
    response_model=PurchaseBookResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_purchase_book_endpoint(
    book_data: PurchaseBookCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PurchaseBookResponse:
    try:
        book = await create_purchase_book(
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
    response_model=PurchaseBookResponse,
)
async def get_purchase_book_endpoint(
    book_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PurchaseBookResponse:
    book = await get_purchase_book(
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
    response_model=list[PurchaseBookResponse],
)
async def get_purchase_books_endpoint(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[PurchaseBookResponse]:
    return await get_purchase_books(db)

@router.patch(
    "/{book_id}",
    response_model=PurchaseBookResponse,
)
async def update_purchase_book_endpoint(
    book_id: int,
    book_data: PurchaseBookUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PurchaseBookResponse:
    book = await get_purchase_book(
        db,
        book_id,
    )
    if book is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="book not found",
        )
    try:
        new_book = await update_purchase_book(
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