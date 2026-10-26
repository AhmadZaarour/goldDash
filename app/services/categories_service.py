from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.categories import Category
from app.schemas.categories import CategoryCreate, CategoryUpdate

async def create_category(
    db: AsyncSession,
    category_data: CategoryCreate,
) -> Category:

    existing_category = await db.scalar(
        select(Category).where(
            Category.name == category_data.name,
        )
    )

    if existing_category is not None:
        raise ValueError("Category name already exists")

    category = Category(
        name=category_data.name,
        description=category_data.description,
    )

    db.add(category)

    await db.commit()
    await db.refresh(category)

    return category

async def get_categories(
        db: AsyncSession,
) -> list[Category]:

    categories = await db.scalars(
        select(Category).order_by(Category.id)
    )

    return list(categories.all())

async def get_category(
    db: AsyncSession,
    category_id: int,
) -> Category | None:

    return await db.scalar(
        select(Category).where(
            Category.id == category_id,
        )
    )

async def update_category(
    db: AsyncSession,
    category: Category,
    category_data: CategoryUpdate,
) -> Category:

    update_data = category_data.model_dump(
        exclude_unset=True,
    )

    if "name" in update_data:
        existing_category = await db.scalar(
            select(Category).where(
                Category.name == update_data["name"],
                Category.id != category.id,
            )
        )

        if existing_category is not None:
            raise ValueError("category SKU already exists")

    for field, value in update_data.items():
        setattr(category, field, value)

    await db.commit()
    await db.refresh(category)

    return category