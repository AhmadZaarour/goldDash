from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

from app.schemas.inventoryBalance import InventoryBalanceResponse

from app.services.inventoryBalance_service import (
    get_inventory_balance,
    get_inventory_balances,
)

router = APIRouter(
    prefix="/balance",
    tags=["Balance"],
)

@router.get(
    "/{balance_id}",
    response_model=InventoryBalanceResponse,
)

async def get_balance_endpoint(
    balance_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InventoryBalanceResponse:
    balance = await get_inventory_balance(
        db,
        balance_id
    )
    if balance is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no balance found",
        )
    return balance

@router.get(
    "",
    response_model=list[InventoryBalanceResponse],
)

async def get_balances_endpoint(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[InventoryBalanceResponse]:
    return await get_inventory_balances(db)