from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.saleBook import SaleBook
from app.schemas.saleBook import SaleBookCreate, SaleBookUpdate

async def create_sale_book(
        db: AsyncSession,
        sale_book_data: SaleBookCreate,
) -> SaleBook:

    existing_book = await db.scalar(
        select(SaleBook).where(
            SaleBook.sale_id == sale_book_data.sale_id,
        )
    )
    if existing_book is not None:
        raise ValueError("book already exist")

    sale_book = SaleBook(
        sale_id=sale_book_data.sale_id,
        recieved_gold_charge=sale_book_data.recieved_gold_charge,
        recieved_making_charge=sale_book_data.recieved_making_charge,
        updated_at=sale_book_data.updated_at,
    )
    db.add(sale_book)
    await db.commit()
    await db.refresh(sale_book)

    return sale_book

async def get_sale_book(
        db: AsyncSession,
        sale_book_id: int,
) -> SaleBook:
    return await db.scalar(
        select(SaleBook).where(
            SaleBook.id == sale_book_id,
        )
    )

async def get_sale_books(
        db: AsyncSession,
) -> list[SaleBook]:
    result = await db.scalars(
        select(SaleBook).order_by(SaleBook.id),
    )
    return list(result.all())

async def update_sale_book(
        db: AsyncSession,
        sale_book: SaleBook,
        book_data: SaleBookUpdate,
) -> SaleBook:
    update_data = book_data.model_dump(
        exclude_unset=True,
    )
    for field, value in update_data.items():
        setattr(sale_book, field, value)

    await db.commit()
    await db.refresh(sale_book)

    return sale_book
