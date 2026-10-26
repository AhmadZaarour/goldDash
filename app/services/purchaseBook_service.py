from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.purchaseBook import PurchaseBook
from app.schemas.purchaseBook import PurchaseBookCreate, PurchaseBookUpdate

async def create_purchase_book(
        db: AsyncSession,
        purchase_book_data: PurchaseBookCreate,
) -> PurchaseBook:
    existing_book = await db.scalar(
        select(PurchaseBook).where(
            PurchaseBook.purchase_id == purchase_book_data.purchase_id,
        )
    )
    if existing_book is not None:
        raise ValueError("book already exist")

    book = PurchaseBook(
        purchase_id=purchase_book_data.purchase_id,
        paid_gold_charge=purchase_book_data.paid_gold_charge,
        paid_making_charge=purchase_book_data.paid_making_charge,
        updated_at=purchase_book_data.updated_at,
    )
    db.add(book)
    await db.commit()
    await db.refresh(book)
    return book


async def get_purchase_book(
        db: AsyncSession,
        purchase_book_id: int,
) -> PurchaseBook | None:
    return await db.scalar(
        select(PurchaseBook).where(
            PurchaseBook.id == purchase_book_id,
        )
    )

async def get_purchase_books(
        db: AsyncSession,
) -> list[PurchaseBook]:
    result = await db.scalars(
        select(PurchaseBook).order_by(PurchaseBook.id),
    )
    return list(result.all())

async def update_purchase_book(
        db: AsyncSession,
        purchase_book: PurchaseBook,
        book_data: PurchaseBookUpdate,
) -> PurchaseBook:
    update_data = book_data.model_dump(
        exclude_unset=True,
    )
    for field, value in update_data.items():
        setattr(purchase_book, field, value)

    await db.commit()
    await db.refresh(purchase_book)

    return purchase_book