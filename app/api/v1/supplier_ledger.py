"""HTTP validation and authorization for supplier accounts."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import AwareDatetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import AdminUser
from app.core.database import get_db
from app.core.dependencies import CurrentUser
from app.schemas.supplier_ledger import (
    AvailabilityResponse,
    LedgerEntryResponse,
    ReversalCreate,
    SettlementCreate,
    SupplierBalanceResponse,
)
from app.services import supplier_ledger_service as service

router = APIRouter(prefix="/suppliers", tags=["Supplier ledger"])


@router.get("/{supplier_id}/availability", response_model=AvailabilityResponse)
async def availability(
    supplier_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: AdminUser,
    location_id: int = Query(gt=0),
    placement: Literal["factory", "showroom"] = "factory",
):
    return await service.availability_service(supplier_id, db, location_id, placement)


@router.get("/{supplier_id}/balance", response_model=SupplierBalanceResponse)
async def get_balance(
    supplier_id: int, db: Annotated[AsyncSession, Depends(get_db)], user: CurrentUser
):
    return await service.get_balance_service(supplier_id, db)


@router.post("/{supplier_id}/settlements", status_code=201, response_model=SupplierBalanceResponse)
async def settle(
    supplier_id: int,
    data: SettlementCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: AdminUser,
):
    return await service.settle_service(supplier_id, data, db, user.id)


@router.get("/{supplier_id}/ledger", response_model=list[LedgerEntryResponse])
async def history(
    supplier_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    response: Response,
    user: CurrentUser,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    purity_id: int | None = Query(None, gt=0),
    kind: Literal["purchase", "sale", "settlement", "reversal"] | None = None,
    from_at: AwareDatetime | None = None,
    to_at: AwareDatetime | None = None,
):
    return await service.history_service(
        supplier_id, db, response, limit, offset, purity_id, kind, from_at, to_at
    )


@router.post(
    "/{supplier_id}/ledger/{entry_id}/reverse", response_model=LedgerEntryResponse, status_code=201
)
async def reverse_settlement(
    supplier_id: int,
    entry_id: int,
    data: ReversalCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: AdminUser,
):
    return await service.reverse_settlement_service(supplier_id, entry_id, data, db, user.id)
