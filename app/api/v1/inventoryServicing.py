from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_role
from app.models.inventoryServicing import InventoryService
from app.models.user import UserRole
from app.schemas.inventoryServicing import (
    ServiceCreate,
    ServiceResponse,
    ServiceUpdate,
)
from app.services.inventoryServicing_service import (
    create_service,
    get_service,
    get_services,
    update_service,
)

router = APIRouter(
    prefix="/servicing",
    tags=["Servicing"],
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.EMPLOYEE))],
)


@router.post(
    "",
    response_model=ServiceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_service_endpoint(
    service_data: ServiceCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ServiceResponse:
    try:
        service = await create_service(
            db,
            service_data,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return service


@router.get(
    "",
    response_model=list[ServiceResponse],
)
async def get_services_endpoint(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ServiceResponse]:
    return await get_services(db)


@router.get(
    "/{barcode}",
    response_model=ServiceResponse,
)
async def get_service_endpoint(
    barcode: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ServiceResponse:
    result = await get_service(db, barcode)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="service not found",
        )
    return result


@router.patch(
    "/{service_id}",
    response_model=ServiceResponse,
)
async def update_service_endpoint(
    service_id: int,
    service_data: ServiceUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ServiceResponse:
    service = await db.get(InventoryService, service_id)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="service not found",
        )
    try:
        new_service = await update_service(
            db,
            service,
            service_data,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return new_service
