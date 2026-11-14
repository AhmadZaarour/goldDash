from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import CashierUser, EmployeeUser
from app.core.database import get_db

from app.services.idempotency import IdempotencyKey
from app.services.transaction_validation import require_active_location
from app.schemas.inventory_operations import (
    ItemReturnCreate,
    ItemTransfer,
    StockTransfer,
    StockTransferResponse,
)
from app.services.inventory_operations_service import (
    transfer_item_service,
    return_item_service,
    transfer_stock_service,
)

router = APIRouter(prefix="/inventory", tags=["Inventory operations"])
Database = Annotated[AsyncSession, Depends(get_db)]

async def active_location(db, location_id):
    try:
        await require_active_location(db, location_id)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@router.post("/items/{item_id}/transfer")
async def transfer_item(item_id: int, data: ItemTransfer, db: Database, user: EmployeeUser) -> dict[str, int | str]:
    return await transfer_item_service(item_id, data, db, user)


@router.post("/returns", status_code=201)
async def return_item(data: ItemReturnCreate, db: Database, user: CashierUser) -> dict[str, int | str | Decimal]:
    return await return_item_service(data, db, user)

@router.post("/stocks/transfer", response_model=StockTransferResponse)
async def transfer_stock(
    data: StockTransfer, db: Database, user: EmployeeUser, idempotency_key: IdempotencyKey
) -> StockTransferResponse:
    return await transfer_stock_service(data, db, user, idempotency_key)
