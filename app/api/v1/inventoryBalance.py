from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.pagination import paginate
from app.models.inventoryBalance import InventoryBalance
from app.schemas.inventoryBalance import InventoryBalanceResponse
from app.services.inventoryBalance_service import (
    get_inventory_balance,
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
    balance = await get_inventory_balance(db, balance_id)
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
    response: Response,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    location_id: int | None = Query(None, gt=0),
    purity_id: int | None = Query(None, gt=0),
    placement: Literal["factory", "showroom"] | None = None,
) -> list[InventoryBalanceResponse]:
    statement = select(InventoryBalance)
    for column, value in [
        (InventoryBalance.location_id, location_id),
        (InventoryBalance.purity_id, purity_id),
        (InventoryBalance.placement, placement),
    ]:
        if value is not None:
            statement = statement.where(column == value)
    return await paginate(db, statement.order_by(InventoryBalance.id), response, limit, offset)
