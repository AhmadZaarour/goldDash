from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cashLedger import CashEntry
from app.models.inventoryBalance import InventoryBalance
from app.models.inventoryItem import InventoryItem
from app.models.saleItem import SaleItem
from app.models.sales import Sale
from app.models.saleStock import SaleStock
from app.schemas.inventory import (
    InventoryMovementCreate,
)
from app.schemas.inventoryBalance import (
    InventoryBalanceUpdate,
)
from app.schemas.sales import (
    SaleCreate,
    SaleStockCreate,
)
from app.services.inventory_service import (
    create_movement,
)
from app.services.inventoryBalance_service import (
    inventory_balance_update,
)
from app.services.supplier_ledger_service import post_entry
from app.services.transaction_validation import require_active_location, require_active_supplier


async def create_item_sale(
    db: AsyncSession,
    sale_data: SaleCreate,
) -> Sale:
    try:
        await require_active_location(db, sale_data.location_id)
    except Exception:
        await db.rollback()
        raise
    sale = Sale(**sale_data.model_dump(exclude={"items"}, exclude_none=True))
    db.add(sale)

    try:
        await db.flush()

        # Lock in a consistent order so overlapping multi-item sales cannot deadlock.
        ids = [line.inventory_item_id for line in sale_data.items]
        if len(ids) != len(set(ids)):
            raise ValueError("An item may appear only once in a sale")
        locked = await db.scalars(
            select(InventoryItem)
            .where(InventoryItem.id.in_(ids))
            .order_by(InventoryItem.id)
            .with_for_update(of=InventoryItem)
        )
        items = {item.id: item for item in locked}
        for line in sale_data.items:
            item = items.get(line.inventory_item_id)
            if item is None:
                raise ValueError(f"Inventory item {line.inventory_item_id} does not exist")
            if item.location_id != sale.location_id:
                raise ValueError("Item is not at the sale location")
            if item.status != "in_stock":
                raise ValueError(f"Inventory item {item.id} is not available for sale")
            db.add(
                SaleItem(
                    sale_id=sale.id,
                    inventory_item_id=item.id,
                    gold_price_per_gram=line.gold_price_per_gram,
                    discount=line.discount,
                    sell_price=line.sell_price,
                )
            )
            item.status = "sold"
            await create_movement(
                db,
                InventoryMovementCreate(
                    inventory_item_id=item.id,
                    movement_type="sale",
                    from_location_id=item.location_id,
                    created_by=sale.created_by,
                    sale_id=sale.id,
                ),
            )
        db.add(
            CashEntry(
                sale_id=sale.id,
                location_id=sale.location_id,
                kind="sale",
                amount_usd=sum((line.sell_price for line in sale_data.items), Decimal("0")),
                created_by=sale.created_by,
            )
        )
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
    try:
        await require_active_location(db, sale_data.location_id)
        await require_active_supplier(db, sale_data.item.supplier_id)
    except Exception:
        await db.rollback()
        raise
    sale = Sale(**sale_data.model_dump(exclude={"item"}, exclude_none=True))
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
            select(InventoryBalance)
            .where(
                InventoryBalance.purity_id == sale_data.item.gold_purity_id,
                InventoryBalance.location_id == sale.location_id,
                InventoryBalance.placement == "factory",
            )
            .with_for_update()
        )
        if balance is None:
            raise ValueError("No factory inventory balance found for this location and purity")

        weight = Decimal(str(sale_data.item.weight))
        if balance.total_weight < weight:
            raise ValueError("Insufficient factory inventory weight")
        updated_balance = InventoryBalanceUpdate(total_weight=balance.total_weight - weight)
        await inventory_balance_update(db, balance, updated_balance)
        post_entry(
            db,
            supplier_id=sale_data.item.supplier_id,
            purity_id=sale_data.item.gold_purity_id,
            gold_grams=-Decimal(str(sale_data.item.gold_charge_in_grams)),
            making_usd=-Decimal(str(sale_data.item.making_charge)),
            source_key=f"sale:{sale.id}",
            kind="sale",
            created_by=sale.created_by,
            sale_id=sale.id,
        )
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
    result = await db.scalars(select(Sale).order_by(Sale.id))
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
