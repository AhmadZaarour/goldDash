from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventoryBalance import InventoryBalance
from app.models.inventoryItem import InventoryItem
from app.models.sales import Sale
from app.models.saleItem import SaleItem
from app.models.saleStock import SaleStock
from app.schemas.inventory import (
    InventoryItemUpdate,
    InventoryMovementUpdate,
)
from app.schemas.inventoryBalance import (
    InventoryBalanceUpdate,
)
from app.schemas.sales import (
    SaleCreate,
    SaleStockCreate,
)
from app.services.inventory_service import (
    update_item,
    get_item,
    update_movement,
    get_movement,
)
from app.services.inventoryBalance_service import (
    inventory_balance_update,
)

async def create_item_sale(
        db: AsyncSession,
        sale_data: SaleCreate,
) -> Sale:
    sale = Sale(
        **sale_data.model_dump(exclude={"items"}, exclude_none=True)
    )
    db.add(sale)

    try:
        await db.flush()

        for line in sale_data.items:
            sale_item = SaleItem(
                sale_id=sale.id,
                inventory_item_id=line.inventory_item_id,
                gold_price_per_gram=line.gold_price_per_gram,
                discount=line.discount,
                sell_price=line.sell_price,
            )
            db.add(sale_item)
            await db.flush()

            item = await get_item(db, sale_item.inventory_item_id)
            item_data = InventoryItemUpdate(
                status="sold",
            )

            await update_item(
                db,
                item,
                item_data,
            )
            movement = await get_movement(db, sale_item.inventory_item_id)
            await update_movement(
                db,
                movement,
                InventoryMovementUpdate(
                    movement_type="sale"
                ),
            )
            inventory_item = await db.scalar(
                select(InventoryItem).where(InventoryItem.id == line.inventory_item_id)
            )
            if inventory_item is None:
                raise ValueError(f"Product {line.inventory_item_id} does not exist")
        await db.flush()
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await db.refresh(sale)
    return sale

async def create_stock_sale(
        db: AsyncSession,
        sale_data: SaleStockCreate,
) -> Sale:
    sale = Sale(
        **sale_data.model_dump(exclude={"item"}, exclude_none=True)
    )
    db.add(sale)
    try:
        await db.flush()

        sale_stock = SaleStock(
            sale_id=sale.id,
            supplier_id=sale_data.item.supplier_id,
            gold_purity_id=sale_data.item.gold_purity_id,
            weight=sale_data.item.weight,
            gold_charge_in_grams=sale_data.item.gold_charge_in_grams,
            making_charge=sale_data.item.making_charge,
        )
        db.add(sale_stock)
        await db.flush()

        balance = await db.scalar(
            select(InventoryBalance).where(
                InventoryBalance.purity_id==sale_data.item.gold_purity_id,
                InventoryBalance.location_id==sale.location_id,
                InventoryBalance.placement=="factory",
            )
        )
        if balance is None:
            raise ValueError("No factory inventory balance found for this location and purity")

        weight = Decimal(str(sale_data.item.weight))
        updated_balance = InventoryBalanceUpdate(
            total_weight=balance.total_weight - weight
        )
        await inventory_balance_update(db, balance, updated_balance)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await db.refresh(sale)
    return sale

async def get_sale(
        db: AsyncSession,
        sale_id: int,
) -> Sale | None:
    return await db.scalar(
        select(Sale).where(
            Sale.id == sale_id,
        )
    )

async def get_sales(
        db: AsyncSession,
) -> list[Sale]:
    result = await db.scalars(
        select(Sale).order_by(Sale.id)
    )
    return list(result.all())

async def get_sale_items(
        db: AsyncSession,
        sale_id: int,
) -> list[SaleItem]:
    result = await db.scalars(
        select(SaleItem).where(
            SaleItem.sale_id == sale_id,
        )
    )
    return list(result.all())

async def get_stock_sale(
        db: AsyncSession,
        sale_id: int,
) -> SaleStock:
    return await db.scalar(
        select(SaleStock).where(
            SaleStock.sale_id == sale_id,
        )
    )