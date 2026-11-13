from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import CashierUser, EmployeeUser
from app.core.database import get_db
from app.core.dependencies import CurrentUser
from app.models.inventoryServicing import ServiceSale
from app.schemas.inventoryServicing import (
    ServiceCreate,
    ServiceResponse,
    ServiceSaleCreate,
    ServiceSaleResponse,
    ServiceUpdate,
)
from app.services import inventoryServicing_service as services
from app.services.idempotency import IdempotencyKey, claim_operation, complete_operation

router = APIRouter(prefix="/servicing", tags=["Servicing"])
Database = Annotated[AsyncSession, Depends(get_db)]


@router.post("", response_model=ServiceResponse, status_code=201)
async def create_service_endpoint(
    data: ServiceCreate,
    db: Database,
    user: EmployeeUser,
    idempotency_key: IdempotencyKey,
):
    receipt, replayed = await claim_operation(db, user.id, "service:create", idempotency_key, data)
    if replayed:
        return ServiceResponse.model_validate(receipt.response_data)
    result = ServiceResponse.model_validate(await services.create_service(db, data))
    await complete_operation(db, receipt, result)
    return result


@router.post("/sales", response_model=ServiceSaleResponse, status_code=201)
async def service_checkout(
    data: ServiceSaleCreate,
    db: Database,
    user: CashierUser,
    idempotency_key: IdempotencyKey,
):
    receipt, replayed = await claim_operation(db, user.id, "service:sale", idempotency_key, data)
    if replayed:
        return ServiceSaleResponse.model_validate(receipt.response_data)
    result = ServiceSaleResponse.model_validate(await services.sell_service(db, data, user.id))
    await complete_operation(db, receipt, result)
    return result


@router.get("/sales", response_model=list[ServiceSaleResponse])
async def service_sales(
    db: Database,
    user: CashierUser,
    location_id: int | None = Query(None, gt=0),
):
    statement = select(ServiceSale).order_by(ServiceSale.id.desc())
    if location_id is not None:
        statement = statement.where(ServiceSale.location_id == location_id)
    return list((await db.scalars(statement)).all())


@router.get("", response_model=list[ServiceResponse])
async def get_services_endpoint(
    db: Database,
    user: CurrentUser,
    barcode: str | None = Query(default=None, min_length=1, max_length=50),
):
    return await services.get_services(db, barcode=barcode)


@router.get("/{barcode}", response_model=ServiceResponse)
async def get_service_endpoint(barcode: str, db: Database, user: CurrentUser):
    result = await services.get_service(db, barcode)
    if result is None:
        raise HTTPException(404, "Service not found")
    return result


@router.patch("/{service_id}", response_model=ServiceResponse)
async def update_service_endpoint(
    service_id: int,
    data: ServiceUpdate,
    db: Database,
    user: EmployeeUser,
):
    return await services.update_service(db, service_id, data)
