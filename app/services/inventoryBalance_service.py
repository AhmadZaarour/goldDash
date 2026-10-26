from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from decimal import Decimal
from app.models.inventoryBalance import InventoryBalance
from app.schemas.inventoryBalance import (
    InventoryBalanceCreate,
    InventoryBalanceUpdate,
)

async def inventory_balance_create(
        db: AsyncSession,
        balance_data: InventoryBalanceCreate,
) -> InventoryBalance:
    
    balance = InventoryBalance(
        purity_id=balance_data.purity_id,
        location_id=balance_data.location_id,
        placement=balance_data.placement,
        total_weight=balance_data.total_weight,
    )
    db.add(balance)
    await db.flush()
    return balance

async def inventory_balance_update(
        db: AsyncSession,
        balance: InventoryBalance,
        balance_data: InventoryBalanceUpdate,
) -> InventoryBalance:

    update_data = balance_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(balance, field, value)
    await db.flush()
    return balance
    
async def get_inventory_balance(
    db: AsyncSession,
    balance_id: int,
) -> InventoryBalance | None:

    return await db.scalar(
        select(InventoryBalance).where(
            InventoryBalance.id == balance_id,
        )
    )

async def get_inventory_balances(
    db: AsyncSession,
) -> list[InventoryBalance]:

    result = await db.scalars(
        select(InventoryBalance).order_by(InventoryBalance.id),
    )

    return list(result.all())