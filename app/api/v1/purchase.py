from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import AdminUser
from app.core.database import get_db
from app.core.pagination import paginate
from app.models.purchase import Purchase
from app.schemas.purchases import (
    PurchaseCreate,
    PurchaseItemResponse,
    PurchaseResponse,
    PurchaseStockCreate,
    PurchaseStockResponse,
)
from app.services.idempotency import IdempotencyKey, claim_operation, complete_operation
from app.services.purchase_service import (
    create_item_purchase,
    create_stock_purchase,
    get_purchase,
    get_purchase_items,
    get_purchase_stock,
)

router = APIRouter(
    prefix="/purchases",
    tags=["Purchases"],
)


@router.post(
    "/item",
    response_model=PurchaseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_items_purchase_endpoint(
    purchase_data: PurchaseCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: AdminUser,
    idempotency_key: IdempotencyKey,
) -> PurchaseResponse:

    receipt, replayed = await claim_operation(
        db, current_user.id, "purchase:item", idempotency_key, purchase_data
    )
    if replayed:
        return PurchaseResponse.model_validate(receipt.response_data)
    purchase_data = purchase_data.model_copy(
        update={"created_by": current_user.id, "created_at": datetime.now(UTC)}
    )
    try:
        purchase = await create_item_purchase(
            db,
            purchase_data,
            commit=False,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    result = PurchaseResponse.model_validate(purchase)
    await complete_operation(db, receipt, result)
    return result


@router.post(
    "/stock",
    response_model=PurchaseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_stock_purchase_endpoint(
    purchase_data: PurchaseStockCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: AdminUser,
    idempotency_key: IdempotencyKey,
) -> PurchaseResponse:
    receipt, replayed = await claim_operation(
        db, current_user.id, "purchase:stock", idempotency_key, purchase_data
    )
    if replayed:
        return PurchaseResponse.model_validate(receipt.response_data)
    purchase_data = purchase_data.model_copy(
        update={"created_by": current_user.id, "created_at": datetime.now(UTC)}
    )
    try:
        purchase = await create_stock_purchase(
            db,
            purchase_data,
            commit=False,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    result = PurchaseResponse.model_validate(purchase)
    await complete_operation(db, receipt, result)
    return result


@router.get(
    "/{purchase_id}",
    response_model=PurchaseResponse,
)
async def get_purchase_endpoint(
    purchase_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PurchaseResponse:
    purchase = await get_purchase(
        db,
        purchase_id,
    )
    if purchase is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="purchase not found",
        )
    return purchase


@router.get(
    "",
    response_model=list[PurchaseResponse],
)
async def list_records(
    db: Annotated[AsyncSession, Depends(get_db)],
    response: Response,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    location_id: int | None = Query(None, gt=0),
    q: str | None = Query(None, min_length=1, max_length=50),
) -> list[PurchaseResponse]:
    statement = select(Purchase)
    if location_id is not None:
        statement = statement.where(Purchase.location_id == location_id)
    if q:
        statement = statement.where(Purchase.invoice_number.icontains(q, autoescape=True))
    return await paginate(db, statement.order_by(Purchase.id), response, limit, offset)


@router.get(
    "/items/{purchase_id}",
    response_model=list[PurchaseItemResponse],
)
async def get_purchase_items_endpoint(
    purchase_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[PurchaseItemResponse]:

    return await get_purchase_items(db, purchase_id)


@router.get(
    "/stock/{purchase_id}",
    response_model=PurchaseStockResponse,
)
async def get_purchase_stock_endpoint(
    purchase_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PurchaseStockResponse:
    purchase = await get_purchase_stock(
        db,
        purchase_id,
    )
    if purchase is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="purchase not found",
        )
    return purchase
