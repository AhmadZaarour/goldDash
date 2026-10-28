from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.purchaseItem import PurchaseItem
from app.models.purchaseStock import PurchaseStock
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

    # Purchase writers hold shared locks on this row until their references commit.
    product = await db.scalar(
        select(Product)
        .where(Product.id == product.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if product is None:
        raise ValueError("Product no longer exists")
    update_data = product_data.model_dump(exclude_unset=True)
    if "inventory_type" in update_data and update_data["inventory_type"] != product.inventory_type:
        item_reference = await db.scalar(
            select(PurchaseItem.id).where(PurchaseItem.product_id == product.id).limit(1)
        )
        stock_reference = await db.scalar(
            select(PurchaseStock.id).where(PurchaseStock.product_id == product.id).limit(1)
        )
        if item_reference is not None or stock_reference is not None:
            raise ValueError("Inventory type cannot change after the product has been purchased")

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
