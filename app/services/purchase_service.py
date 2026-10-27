from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventoryBalance import InventoryBalance
from app.models.product import Product
from app.models.purchase import Purchase
from app.models.purchaseItem import PurchaseItem
from app.models.purchaseStock import PurchaseStock
from app.schemas.inventory import (
    InventoryItemCreate,
    InventoryMovementCreate,
    InventoryStockCreate,
)
from app.schemas.purchases import (
    PurchaseCreate,
    PurchaseStockCreate,
)
from app.services.inventory_service import (
    create_item,
    create_movement,
    create_stock,
)
from app.services.supplier_ledger_service import post_entry


async def create_item_purchase(
    db: AsyncSession,
    purchase_data: PurchaseCreate,
) -> Purchase:
    purchase = Purchase(**purchase_data.model_dump(exclude={"items"}, exclude_none=True))
    db.add(purchase)

    try:
        await db.flush()

        totals = {}
        for line in purchase_data.items:
            purchase_item = PurchaseItem(
                supplier_id=line.supplier_id,
                purchase_id=purchase.id,
                product_id=line.product_id,
                weight=line.weight,
                gold_price_per_gram=line.gold_price_per_gram,
                gold_charge_in_grams=line.gold_charge_in_grams,
                making_charge=line.making_charge,
            )
            db.add(purchase_item)
            await db.flush()

            item = await create_item(
                db,
                InventoryItemCreate(
                    purchase_item_id=purchase_item.id,
                    location_id=purchase.location_id,
                    barcode=line.barcode,
                    status="in_stock",
                ),
            )

            await create_movement(
                db,
                InventoryMovementCreate(
                    inventory_item_id=item.id,
                    movement_type="purchase",
                    to_location_id=purchase.location_id,
                    created_by=purchase.created_by,
                ),
            )

            product = await db.scalar(select(Product).where(Product.id == line.product_id))
            if product is None:
                raise ValueError(f"Product {line.product_id} does not exist")
            grams, usd = totals.get(product.purity_id, (Decimal("0"), Decimal("0")))
            totals[product.purity_id] = (
                grams + Decimal(str(line.gold_charge_in_grams)),
                usd + Decimal(str(line.making_charge)),
            )
        for purity_id, (grams, usd) in totals.items():
            post_entry(
                db,
                supplier_id=purchase.supplier_id,
                purity_id=purity_id,
                gold_grams=grams,
                making_usd=usd,
                source_key=f"purchase:{purchase.id}:{purity_id}",
                kind="purchase",
                created_by=purchase.created_by,
                purchase_id=purchase.id,
            )

        await db.flush()
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    await db.refresh(purchase)
    return purchase


async def create_stock_purchase(
    db: AsyncSession,
    purchase_data: PurchaseStockCreate,
) -> Purchase:
    purchase = Purchase(**purchase_data.model_dump(exclude={"item"}, exclude_none=True))
    db.add(purchase)
    try:
        await db.flush()

        purchase_stock = PurchaseStock(
            purchase_id=purchase.id,
            product_id=purchase_data.item.product_id,
            stock_for=purchase_data.item.stock_for,
            weight=purchase_data.item.weight,
            cost_per_gram=purchase_data.item.cost_per_gram,
        )
        db.add(purchase_stock)
        await db.flush()

        await create_stock(
            db,
            InventoryStockCreate(
                purchase_stock_id=purchase_stock.id,
            ),
        )

        product = await db.scalar(
            select(Product).where(Product.id == purchase_data.item.product_id)
        )
        if product is None:
            raise ValueError(f"Product {purchase_data.item.product_id} does not exist")
        statement = insert(InventoryBalance).values(
            purity_id=product.purity_id,
            location_id=purchase.location_id,
            placement=purchase_data.item.stock_for,
            total_weight=Decimal(str(purchase_data.item.weight)),
        )
        await db.execute(
            statement.on_conflict_do_update(
                constraint="uq_balance_bucket",
                set_={
                    "total_weight": InventoryBalance.total_weight + statement.excluded.total_weight
                },
            )
        )
        post_entry(
            db,
            supplier_id=purchase.supplier_id,
            purity_id=product.purity_id,
            gold_grams=purchase_data.item.weight,
            making_usd=purchase_data.item.making_charge,
            source_key=f"purchase:{purchase.id}:{product.purity_id}",
            kind="purchase",
            created_by=purchase.created_by,
            purchase_id=purchase.id,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await db.refresh(purchase)
    return purchase


async def get_purchase(
    db: AsyncSession,
    purchase_id: int,
) -> Purchase | None:
    return await db.scalar(
        select(Purchase).where(
            Purchase.id == purchase_id,
        )
    )


async def get_purchases(
    db: AsyncSession,
) -> list[Purchase]:
    result = await db.scalars(select(Purchase).order_by(Purchase.id))
    return list(result.all())


async def get_purchase_items(
    db: AsyncSession,
    purchase_id: int,
) -> list[PurchaseItem]:
    result = await db.scalars(
        select(PurchaseItem).where(
            PurchaseItem.purchase_id == purchase_id,
        )
    )
    return list(result.all())


async def get_purchase_stock(
    db: AsyncSession,
    purchase_id: int,
) -> PurchaseStock:
    return await db.scalar(
        select(PurchaseStock).where(
            PurchaseStock.purchase_id == purchase_id,
        )
    )
