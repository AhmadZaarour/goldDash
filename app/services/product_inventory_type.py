from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import InventoryType, Product


async def validate_purchase_product(
    db: AsyncSession, product_id: int, expected_type: InventoryType | str
) -> Product:
    """Keep type stable while purchase references are written, without serializing readers."""
    product = await db.scalar(
        select(Product)
        .where(Product.id == product_id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    if product is None:
        raise ValueError(f"Product {product_id} does not exist")
    if product.inventory_type != expected_type:
        raise ValueError(f"Product {product_id} must have inventory type '{expected_type}'")
    return product
