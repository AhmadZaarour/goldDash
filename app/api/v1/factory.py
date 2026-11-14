"""Factory workflows use weight; piece registration belongs to showroom receipt."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import AdminUser, EmployeeUser
from app.core.database import get_db
from app.core.dependencies import CurrentUser
from app.core.workspace import require_workspace
from app.models import FinishedGoldLot
from app.models.operations import InternalInvoice
from app.schemas.factory import (
    FactorySaleCreate,
    FinishedSeed,
    ProductionFinish,
    ProductionStart,
    ProductionStep,
    ShowroomReceive,
    WeightSupplyCreate,
)
from app.services import factory_service as service
from app.services.idempotency import IdempotencyKey
from app.services.item_photos_service import stage_photo_service
from app.services.operations_service import execute

router = APIRouter(prefix="/operations", tags=["Factory weight workflows"])
Database = Annotated[AsyncSession, Depends(get_db)]


@router.post("/weight-production", status_code=201)
async def start(data: ProductionStart, db: Database, user: EmployeeUser, key: IdempotencyKey):
    require_workspace("factory")
    return await execute(
        db,
        user.id,
        "production:weight:start",
        key,
        data,
        lambda: service.start_production(db, data, user.id),
    )


@router.post("/weight-production/{batch_id}/steps", status_code=201)
async def step(
    batch_id: int, data: ProductionStep, db: Database, user: EmployeeUser, key: IdempotencyKey
):
    require_workspace("factory")
    return await execute(
        db,
        user.id,
        f"production:weight:{batch_id}:step",
        key,
        data,
        lambda: service.add_step(db, batch_id, data, user.id),
    )


@router.post("/weight-production/{batch_id}/finish", status_code=201)
async def finish(
    batch_id: int, data: ProductionFinish, db: Database, user: EmployeeUser, key: IdempotencyKey
):
    require_workspace("factory")
    return await execute(
        db,
        user.id,
        f"production:weight:{batch_id}:finish",
        key,
        data,
        lambda: service.finish_production(db, batch_id, data, user.id),
    )


@router.get("/finished-stock")
async def finished_stock(
    db: Database, user: CurrentUser, location_id: int | None = Query(None, gt=0)
):
    return await service.stock(db, location_id)


@router.post("/finished-opening", status_code=201)
async def seed(data: FinishedSeed, db: Database, user: AdminUser, key: IdempotencyKey):
    require_workspace("factory")
    return await execute(
        db, user.id, "finished:opening", key, data, lambda: service.seed_finished(db, data, user.id)
    )


@router.post("/supplier-weight-sales", status_code=201)
async def supplier_sale(
    data: FactorySaleCreate, db: Database, user: AdminUser, key: IdempotencyKey
):
    require_workspace("factory")
    return await execute(
        db, user.id, "supplier:weight", key, data, lambda: service.supplier_sale(db, data, user.id)
    )


@router.get("/supplier-weight-sales/{sale_id}")
async def supplier_detail(sale_id: int, db: Database, user: CurrentUser):
    try:
        return await service.sale_detail(db, sale_id)
    except ValueError as error:
        raise HTTPException(404, str(error)) from error


@router.post("/weight-internal-invoices", status_code=201)
async def supply(data: WeightSupplyCreate, db: Database, user: AdminUser, key: IdempotencyKey):
    require_workspace("factory")
    return await execute(
        db,
        user.id,
        "internal:weight",
        key,
        data,
        lambda: service.supply_showroom(db, data, user.id),
        paired=True,
    )


@router.get("/pending-receipts")
async def pending(db: Database, user: CurrentUser):
    require_workspace("showroom")
    return await service.pending_receipts(db)


@router.post("/weight-internal-invoices/{invoice_id}/photos", status_code=201)
async def receipt_photo(invoice_id: int, request: Request, db: Database, user: EmployeeUser):
    require_workspace("showroom")
    invoice = await db.get(InternalInvoice, invoice_id)
    if invoice is None or invoice.tracking_mode != "weight" or invoice.reversal_of_id is not None:
        raise HTTPException(404, "Weight supply invoice not found")
    reversed_invoice = await db.scalar(
        select(InternalInvoice.id).where(InternalInvoice.reversal_of_id == invoice.id)
    )
    pending_weight = await db.scalar(
        select(FinishedGoldLot.id)
        .where(
            FinishedGoldLot.invoice_id == invoice.id,
            FinishedGoldLot.remaining_weight > 0,
        )
        .limit(1)
    )
    if reversed_invoice or pending_weight is None:
        raise HTTPException(409, "This invoice has no pending showroom receipt")
    return await stage_photo_service(request, db, user)


@router.post("/weight-internal-invoices/{invoice_id}/receive", status_code=201)
async def receive(
    invoice_id: int, data: ShowroomReceive, db: Database, user: EmployeeUser, key: IdempotencyKey
):
    require_workspace("showroom")
    return await execute(
        db,
        user.id,
        f"internal:receive:{invoice_id}",
        key,
        data,
        lambda: service.receive_showroom(db, invoice_id, data, user.id),
    )
