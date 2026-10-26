from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.customers import CustomerCreate, CustomerUpdate, CustomerResponse
from app.services.customers_service import (
    create_customer,
    update_customer,
    get_customer,
    get_customers
)

router = APIRouter(
    prefix="/customers",
    tags=["Customers"],
)

@router.post(
    "",
    response_model=CustomerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_customer_endpoint(
    customer_data: CustomerCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CustomerResponse:

    try:
        customer = await create_customer(
            db,
            customer_data,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return customer

@router.get(
    "",
    response_model=list[CustomerResponse],
)
async def list_customers(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[CustomerResponse]:

    return await get_customers(db)


@router.get(
    "/{customer_id}",
    response_model=CustomerResponse,
)
async def get_customer_endpoint(
    customer_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CustomerResponse:

    customer = await get_customer(
        db,
        customer_id,
    )

    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="customer not found",
        )

    return customer

@router.patch(
    "/{customer_id}",
    response_model=CustomerResponse,
)
async def update_customer_endpoint(
    customer_id: int,
    customer_data: CustomerUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CustomerResponse:

    customer = await get_customer(
        db,
        customer_id,
    )

    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="customer not found",
        )

    try:
        new_customer = await update_customer(
            db,
            customer,
            customer_data,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    return new_customer