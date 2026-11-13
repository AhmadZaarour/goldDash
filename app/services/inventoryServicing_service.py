from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cashLedger import CashEntry
from app.models.inventoryServicing import InventoryService, ServiceSale
from app.schemas.inventoryServicing import ServiceCreate, ServiceSaleCreate, ServiceUpdate
from app.services.transaction_validation import require_active_location


async def create_service(db: AsyncSession, data: ServiceCreate) -> InventoryService:
    service = InventoryService(
        notes=data.notes,
        barcode="SV" + uuid4().hex[:20].upper(),
        status=data.status,
    )
    db.add(service)
    await db.flush()
    await db.refresh(service)
    return service


async def update_service(db: AsyncSession, service_id: int, data: ServiceUpdate):
    service = await db.scalar(
        select(InventoryService).where(InventoryService.id == service_id).with_for_update()
    )
    if service is None:
        raise HTTPException(404, "Service not found")
    if await db.scalar(select(ServiceSale.id).where(ServiceSale.service_id == service.id)):
        raise HTTPException(409, "A paid service cannot be changed")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(service, field, value)
    await db.commit()
    await db.refresh(service)
    return service


async def sell_service(db: AsyncSession, data: ServiceSaleCreate, user_id: int):
    try:
        await require_active_location(db, data.location_id)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    service = await db.scalar(
        select(InventoryService).where(InventoryService.barcode == data.barcode).with_for_update()
    )
    if service is None:
        raise HTTPException(404, "Service not found")
    # Query after obtaining the lock: a concurrent checkout may have just committed.
    if await db.scalar(select(ServiceSale.id).where(ServiceSale.service_id == service.id)):
        raise HTTPException(409, "This service has already been paid")
    if service.status != "finished":
        raise HTTPException(409, "Finish the service before collecting payment")
    sale = ServiceSale(
        service_id=service.id,
        barcode=service.barcode,
        notes=service.notes,
        location_id=data.location_id,
        amount_usd=data.cost,
        created_by=user_id,
    )
    db.add(sale)
    await db.flush()
    db.add(
        CashEntry(
            service_sale_id=sale.id,
            location_id=data.location_id,
            kind="service_sale",
            amount_usd=data.cost,
            created_by=user_id,
            description=f"Service {service.barcode}",
        )
    )
    await db.flush()
    await db.refresh(sale)
    return sale


async def get_services(db: AsyncSession, *, barcode: str | None = None):
    statement = select(InventoryService).order_by(InventoryService.id)
    if barcode is not None:
        statement = statement.where(InventoryService.barcode == barcode)
    return list((await db.scalars(statement)).all())


async def get_service(db: AsyncSession, barcode: str):
    return await db.scalar(select(InventoryService).where(InventoryService.barcode == barcode))
