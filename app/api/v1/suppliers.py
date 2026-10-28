from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_role
from app.core.pagination import paginate
from app.models.suppliers import Supplier
from app.models.user import UserRole
from app.schemas.suppliers import SupplierCreate, SupplierResponse, SupplierUpdate
from app.services.suppliers_service import (
    create_supplier,
    get_supplier,
    update_supplier,
)

router = APIRouter(
    prefix="/suppliers",
    tags=["Suppliers"],
)


@router.post(
    "",
    dependencies=[Depends(require_role(UserRole.ADMIN))],
    response_model=SupplierResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_supplier_endpoint(
    supplier_data: SupplierCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SupplierResponse:

    try:
        supplier = await create_supplier(
            db,
            supplier_data,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return supplier


@router.get(
    "",
    response_model=list[SupplierResponse],
)
async def list_records(
    db: Annotated[AsyncSession, Depends(get_db)],
    response: Response,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None, min_length=1, max_length=100),
) -> list[SupplierResponse]:
    statement = select(Supplier).order_by(Supplier.id)
    if q:
        statement = statement.where(Supplier.name.icontains(q, autoescape=True))
    return await paginate(db, statement, response, limit, offset)


@router.get(
    "/{supplier_id}",
    response_model=SupplierResponse,
)
async def get_supplier_endpoint(
    supplier_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SupplierResponse:

    supplier = await get_supplier(
        db,
        supplier_id,
    )

    if supplier is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="supplier not found",
        )

    return supplier


@router.patch(
    "/{supplier_id}",
    dependencies=[Depends(require_role(UserRole.ADMIN))],
    response_model=SupplierResponse,
)
async def update_supplier_endpoint(
    supplier_id: int,
    supplier_data: SupplierUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SupplierResponse:

    supplier = await get_supplier(
        db,
        supplier_id,
    )

    if supplier is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="supplier not found",
        )

    try:
        new_supplier = await update_supplier(
            db,
            supplier,
            supplier_data,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return new_supplier
