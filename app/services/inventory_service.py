from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventoryItem import InventoryItem
from app.models.inventoryMovement import InventoryMovement
from app.models.inventoryStock import InventoryStock
from app.schemas.inventory import (
    InventoryItemCreate,
    InventoryItemUpdate,
    InventoryMovementCreate,
    InventoryMovementUpdate,
    InventoryStockCreate,
    InventoryStockUpdate,
)


async def create_item(
    db: AsyncSession,
    item_data: InventoryItemCreate,
) -> InventoryItem:

    existing_item = await db.scalar(
        select(InventoryItem).where(InventoryItem.barcode == item_data.barcode)
    )

    if existing_item is not None:
        raise ValueError("Item barcode already exists")

    item = InventoryItem(
        purchase_item_id=item_data.purchase_item_id,
        location_id=item_data.location_id,
        barcode=item_data.barcode,
        image_url=str(item_data.image_url) if item_data.image_url is not None else None,
        status=item_data.status,
    )

    db.add(item)
    await db.flush()

    return item


async def get_items(
    db: AsyncSession,
) -> list[InventoryItem]:
    result = await db.scalars(select(InventoryItem).order_by(InventoryItem.id))

    return list(result.all())


async def get_item(
    db: AsyncSession,
    item_id: int,
) -> InventoryItem | None:
    return await db.scalar(select(InventoryItem).where(InventoryItem.id == item_id))


async def update_item(
    db: AsyncSession,
    item: InventoryItem,
    item_data: InventoryItemUpdate,
) -> InventoryItem:
    update_data = item_data.model_dump(
        exclude_unset=True,
    )
    if "barcode" in update_data and update_data["barcode"] != item.barcode:
        existing_item = await db.scalar(
            select(InventoryItem).where(
                InventoryItem.barcode == update_data["barcode"],
                InventoryItem.id != item.id,
            )
        )
        if existing_item is not None:
            raise ValueError("Item barcode already exists")

    for field, value in update_data.items():
        if field == "image_url" and value is not None:
            value = str(value)
        setattr(item, field, value)

    await db.flush()

    return item


async def create_stock(
    db: AsyncSession,
    stock_data: InventoryStockCreate,
) -> InventoryStock:

    stock = InventoryStock(
        purchase_stock_id=stock_data.purchase_stock_id,
    )
    db.add(stock)
    await db.flush()
    return stock


async def get_stock(
    db: AsyncSession,
    stock_id: int,
) -> InventoryStock | None:
    return await db.scalar(select(InventoryStock).where(InventoryStock.id == stock_id))


async def get_all_stock(
    db: AsyncSession,
) -> list[InventoryStock]:
    result = await db.scalars(select(InventoryStock).order_by(InventoryStock.id))
    return list(result.all())


async def update_stock(
    db: AsyncSession,
    stock: InventoryStock,
    stock_data: InventoryStockUpdate,
) -> InventoryStock:
    update_data = stock_data.model_dump(
        exclude_unset=True,
    )

    for field, value in update_data.items():
        setattr(stock, field, value)

    await db.flush()

    return stock


async def create_movement(
    db: AsyncSession,
    movement_data: InventoryMovementCreate,
) -> InventoryMovement:

    movement = InventoryMovement(
        inventory_item_id=movement_data.inventory_item_id,
        movement_type=movement_data.movement_type,
        from_location_id=movement_data.from_location_id,
        to_location_id=movement_data.to_location_id,
        created_by=movement_data.created_by,
        sale_id=movement_data.sale_id,
    )
    db.add(movement)
    await db.flush()
    return movement


async def get_movement(
    db: AsyncSession,
    movement_id: int,
) -> InventoryMovement | None:
    return await db.scalar(select(InventoryMovement).where(InventoryMovement.id == movement_id))


async def get_all_movements(
    db: AsyncSession,
) -> list[InventoryMovement]:
    result = await db.scalars(select(InventoryMovement).order_by(InventoryMovement.id))
    return list(result.all())


async def update_movement(
    db: AsyncSession,
    movement: InventoryMovement,
    movement_data: InventoryMovementUpdate,
) -> InventoryMovement:
    update_data = movement_data.model_dump(
        exclude_unset=True,
    )

    for field, value in update_data.items():
        setattr(movement, field, value)

    await db.flush()

    return movement
