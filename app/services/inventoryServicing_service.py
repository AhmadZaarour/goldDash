from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.inventoryServicing import InventoryService
from app.schemas.inventoryServicing import ServiceCreate, ServiceUpdate

async def create_service(
        db: AsyncSession,
        service_data: ServiceCreate,
) -> InventoryService:
    existing = await db.scalar(
        select(InventoryService).where(
            InventoryService.barcode == service_data.barcode
        )
    )
    if existing is not None:
        raise ValueError("service already exist")

    service = InventoryService(
        notes=service_data.notes,
        customer_id=service_data.customer_id,
        barcode=service_data.barcode,
        status=service_data.status,
        cost=service_data.cost,
    )

    db.add(service)
    await db.commit()
    await db.refresh(service)
    return service

async def update_service(
        db: AsyncSession,
        service: InventoryService,
        service_data: ServiceUpdate,
) -> InventoryService:
     
    updated_data = service_data.model_dump(
        exclude_unset=True,
    )

    for field, value in updated_data.items():
        setattr(service, field, value)

    await db.commit()
    await db.refresh(service)
    return service

async def get_services(
        db: AsyncSession
) -> list[InventoryService]:
    result = await db.scalars(
        select(InventoryService).order_by(InventoryService.id)
    )
    return list(result.all())

async def get_service(
        db: AsyncSession,
        barcode: str,
) -> InventoryService:
    return await db.scalar(
        select(InventoryService).where(
            InventoryService.barcode == barcode
        )
    )