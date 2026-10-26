from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.suppliers import SupplierUpdate, SupplierCreate, SupplierResponse
from app.services.suppliers_service import (
    create_supplier,
    get_supplier,
    get_suppliers,
    update_supplier,
)

router = APIRouter(
    prefix="/suppliers",
    tags=["Suppliers"],
)

@router.post(
    "",
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
async def list_suppliers(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[SupplierResponse]:

    return await get_suppliers(db)

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