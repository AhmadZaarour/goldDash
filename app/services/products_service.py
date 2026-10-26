from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.schemas.products import ProductCreate, ProductUpdate


async def create_product(
    db: AsyncSession,
    product_data: ProductCreate,
) -> Product:

    existing_product = await db.scalar(
        select(Product).where(
            Product.sku == product_data.sku,
        )
    )

    if existing_product is not None:
        raise ValueError("Product SKU already exists")

    product = Product(
        sku=product_data.sku,
        name=product_data.name,
        description=product_data.description,
        category_id=product_data.category_id,
        purity_id=product_data.purity_id,
        inventory_type=product_data.inventory_type,
    )

    db.add(product)

    await db.commit()
    await db.refresh(product)

    return product


async def get_product(
    db: AsyncSession,
    product_id: int,
) -> Product | None:

    return await db.scalar(
        select(Product).where(
            Product.id == product_id,
        )
    )


async def get_products(
    db: AsyncSession,
) -> list[Product]:

    result = await db.scalars(
        select(Product).order_by(Product.id),
    )

    return list(result.all())


async def update_product(
    db: AsyncSession,
    product: Product,
    product_data: ProductUpdate,
) -> Product:

    update_data = product_data.model_dump(
        exclude_unset=True,
    )

    if "sku" in update_data:
        existing_product = await db.scalar(
            select(Product).where(
                Product.sku == update_data["sku"],
                Product.id != product.id,
            )
        )

        if existing_product is not None:
            raise ValueError("Product SKU already exists")

    for field, value in update_data.items():
        setattr(product, field, value)

    await db.commit()
    await db.refresh(product)

    return product