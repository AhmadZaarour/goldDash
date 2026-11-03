from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cashLedger import CashEntry
from app.models.goldPurities import GoldPurity
from app.models.inventoryBalance import InventoryBalance
from app.models.photoUpload import PhotoUpload
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
from app.services.gold_conversion import allocate_charge, canonical_purity, grams24, purchase_factor
from app.services.gold_price import get_quote, price_per_gram, require_fresh_quote
from app.services.inventory_service import (
    create_item,
    create_movement,
    create_stock,
)
from app.services.product_inventory_type import validate_purchase_product
from app.services.settlement_resources import available_cash
from app.services.supplier_ledger_service import post_entry
from app.services.transaction_validation import require_active_location, require_active_supplier


async def create_item_purchase(
    db: AsyncSession,
    purchase_data: PurchaseCreate,
    *,
    commit: bool = True,
) -> Purchase:
    try:
        await require_active_location(db, purchase_data.location_id)
        await require_active_supplier(db, purchase_data.supplier_id)
        products = {
            product_id: await validate_purchase_product(db, product_id, "item")
            for product_id in sorted({line.product_id for line in purchase_data.items})
        }
    except Exception:
        await db.rollback()
        raise
    physical_total = sum((line.weight for line in purchase_data.items), Decimal(0))
    if purchase_data.total_gold_charge_grams != physical_total:
        raise ValueError("Total gold charge must equal the total purchased item weight")
    purities = {p.purity_id: await db.get(GoldPurity, p.purity_id) for p in products.values()}
    factors = [
        purchase_factor(purities[products[line.product_id].purity_id])
        for line in purchase_data.items
    ]
    fine = [line.weight * factor for line, factor in zip(purchase_data.items, factors, strict=True)]
    fine_total = sum(fine, Decimal(0))
    debt = grams24(fine_total, Decimal(1))
    canonical = await canonical_purity(db)
    quote = await get_quote()
    require_fresh_quote(quote)
    purchase = Purchase(
        **purchase_data.model_dump(exclude={"items"}, exclude_none=True),
        gold_debt_24k=debt,
        gold_quote_at=datetime.fromisoformat(quote["fetched_at"]),
    )
    db.add(purchase)

    try:
        await db.flush()

        allocations = allocate_charge(physical_total, fine)
        for index, line in enumerate(purchase_data.items):
            charge = allocations[index]
            purchase_item = PurchaseItem(
                supplier_id=line.supplier_id,
                purchase_id=purchase.id,
                product_id=line.product_id,
                weight=line.weight,
                valuation_factor=factors[index],
                gold_price_per_gram=price_per_gram(
                    quote, purities[products[line.product_id].purity_id]
                ),
                gold_charge_in_grams=charge,
                making_charge=line.making_charge,
            )
            db.add(purchase_item)
            await db.flush()

            item = await create_item(
                db,
                InventoryItemCreate(
                    purchase_item_id=purchase_item.id,
                    location_id=purchase.location_id,
                    image_url=line.image_url,
                    status="in_stock",
                ),
            )

            if line.photo_token:
                upload = await db.scalar(
                    select(PhotoUpload)
                    .where(PhotoUpload.token == line.photo_token)
                    .with_for_update()
                )
                if (
                    upload is None
                    or upload.created_by != purchase.created_by
                    or upload.inventory_item_id is not None
                    or upload.expires_at <= datetime.now(UTC)
                ):
                    raise ValueError("Purchase photo is unavailable or expired; upload it again")
                upload.inventory_item_id = item.id
                item.image_url = f"/api/v1/media/items/{upload.filename}"
            await create_movement(
                db,
                InventoryMovementCreate(
                    inventory_item_id=item.id,
                    movement_type="purchase",
                    to_location_id=purchase.location_id,
                    created_by=purchase.created_by,
                ),
            )

        entry = await post_entry(
            db,
            supplier_id=purchase.supplier_id,
            purity_id=canonical.id,
            gold_grams=debt,
            gold_24k=debt,
            making_usd=sum((line.making_charge for line in purchase_data.items), Decimal(0)),
            source_key=f"purchase:{purchase.id}:invoice",
            kind="purchase",
            created_by=purchase.created_by,
            purchase_id=purchase.id,
        )
        entry.note = "Invoice weight converted using snapshotted item purity factors"

        await db.flush()
        if commit:
            await db.commit()
    except Exception:
        await db.rollback()
        raise

    await db.refresh(purchase)
    return purchase


async def create_stock_purchase(
    db: AsyncSession,
    purchase_data: PurchaseStockCreate,
    *,
    commit: bool = True,
) -> Purchase:
    """Create legacy bulk invoices; new supplier bulk purchases are retired."""
    try:
        await require_active_location(db, purchase_data.location_id)
        await require_active_supplier(db, purchase_data.supplier_id)
        product = await validate_purchase_product(db, purchase_data.item.product_id, "bulk")
    except Exception:
        await db.rollback()
        raise
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
        await post_entry(
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
        await db.flush()
        if commit:
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


async def create_customer_bulk_purchase(db, data, user_id):
    await require_active_location(db, data.location_id, exclusive=True)
    product = await validate_purchase_product(db, data.product_id, "bulk")
    if data.paid_usd and await available_cash(db, data.location_id) < data.paid_usd:
        raise ValueError("Insufficient cash in the selected drawer")
    purity = await db.get(GoldPurity, product.purity_id)
    quote = await get_quote()
    require_fresh_quote(quote)
    purchase = Purchase(
        source="customer" if data.paid_usd else "opening",
        supplier_id=None,
        location_id=data.location_id,
        invoice_number=data.invoice_number,
        notes=data.notes,
        created_by=user_id,
        created_at=datetime.now(UTC),
        paid_usd=data.paid_usd,
        gold_quote_at=datetime.fromisoformat(quote["fetched_at"]),
    )
    db.add(purchase)
    await db.flush()
    stock = PurchaseStock(
        purchase_id=purchase.id,
        product_id=data.product_id,
        stock_for=data.placement,
        weight=data.weight,
        gold_price_per_gram=price_per_gram(quote, purity),
        cost_per_gram=(data.paid_usd / data.weight).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        ),
    )
    db.add(stock)
    await db.flush()
    await create_stock(db, InventoryStockCreate(purchase_stock_id=stock.id))
    statement = insert(InventoryBalance).values(
        purity_id=product.purity_id,
        location_id=data.location_id,
        placement=data.placement,
        total_weight=data.weight,
    )
    await db.execute(
        statement.on_conflict_do_update(
            constraint="uq_balance_bucket",
            set_={"total_weight": InventoryBalance.total_weight + statement.excluded.total_weight},
        )
    )
    if data.paid_usd:
        db.add(
            CashEntry(
                purchase_id=purchase.id,
                location_id=data.location_id,
                kind="customer_purchase",
                amount_usd=-data.paid_usd,
                created_by=user_id,
                description="Walk-in customer bulk purchase",
            )
        )
    await db.flush()
    return purchase
