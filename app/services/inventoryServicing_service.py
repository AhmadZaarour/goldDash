from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.workspace import active_unit
from app.models.cashLedger import CashEntry
from app.models.inventoryServicing import InventoryService, ServiceSale
from app.schemas.inventoryServicing import (
    ServiceCreate,
    ServicePaymentCorrection,
    ServiceSaleCreate,
    ServiceUpdate,
)
from app.services.barcodes import BARCODE_ATTEMPTS, generate_barcode
from app.services.cash_service import lock_cash_drawer, require_unreconciled_entry
from app.services.settlement_resources import available_cash
from app.services.transaction_validation import require_active_location


async def create_service(db: AsyncSession, data: ServiceCreate) -> InventoryService:
    for _ in range(BARCODE_ATTEMPTS):
        statement = (
            insert(InventoryService)
            .values(
                unit=active_unit(),
                notes=data.notes,
                barcode=generate_barcode("SV"),
                status=data.status,
            )
            .on_conflict_do_nothing(index_elements=[InventoryService.barcode])
            .returning(InventoryService)
        )
        service = await db.scalar(statement)
        if service is not None:
            await db.refresh(service)
            return service
    raise HTTPException(409, "Could not generate a unique service barcode. Retry service intake.")


async def lock_service(db: AsyncSession, service_id: int) -> InventoryService:
    service = await db.scalar(
        select(InventoryService).where(InventoryService.id == service_id).with_for_update()
    )
    if service is None:
        raise HTTPException(404, "Service not found")
    return service


async def update_service(
    db: AsyncSession, service_id: int, data: ServiceUpdate, *, admin: bool = False
):
    service = await lock_service(db, service_id)
    changes = data.model_dump(exclude_unset=True)
    if await db.scalar(select(ServiceSale.id).where(ServiceSale.service_id == service.id)) and (
        not admin or "status" in changes
    ):
        raise HTTPException(409, "A paid service cannot be changed")
    for field, value in changes.items():
        setattr(service, field, value)
    await db.commit()
    await db.refresh(service)
    return service


async def delete_service(db: AsyncSession, service_id: int) -> None:
    service = await lock_service(db, service_id)
    if await db.scalar(select(ServiceSale.id).where(ServiceSale.service_id == service.id)):
        raise HTTPException(409, "Void the service payment before deleting the job")
    await db.delete(service)
    await db.commit()


async def correct_service_payment(
    db: AsyncSession, sale_id: int, data: ServicePaymentCorrection | None
) -> ServiceSale | None:
    link = (
        await db.execute(
            select(ServiceSale.location_id, ServiceSale.service_id).where(ServiceSale.id == sale_id)
        )
    ).one_or_none()
    if link is None:
        raise HTTPException(404, "Service payment not found")
    await lock_cash_drawer(db, link.location_id)
    await lock_service(db, link.service_id)
    sale = await db.scalar(select(ServiceSale).where(ServiceSale.id == sale_id).with_for_update())
    if sale is None:
        raise HTTPException(404, "Service payment not found")
    cash_entry = await db.scalar(
        select(CashEntry).where(CashEntry.service_sale_id == sale_id).with_for_update()
    )
    if (
        cash_entry is None
        or cash_entry.location_id != sale.location_id
        or cash_entry.amount_usd != sale.amount_usd
    ):
        raise HTTPException(409, "The cash entry does not match this payment")
    if data is not None and data.cost == sale.amount_usd:
        return sale
    await require_unreconciled_entry(db, cash_entry)
    reduction = sale.amount_usd - (data.cost if data is not None else 0)
    if reduction > 0 and await available_cash(db, sale.location_id) < reduction:
        raise HTTPException(409, "Insufficient cash in the original drawer to correct this payment")
    if data is None:
        await db.delete(cash_entry)
        await db.flush()
        await db.delete(sale)
    else:
        sale.amount_usd = data.cost
        cash_entry.amount_usd = data.cost
    await db.commit()
    return sale if data is not None else None


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
