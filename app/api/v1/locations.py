from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.locations import LocationCreate, LocationResponse, LocationUpdate
from app.services.locations_service import (
    create_location,
    get_location,
    update_location,
)

router = APIRouter(
    prefix="/locations",
    tags=["Locations"],
)

@router.post(
    "",
    response_model=LocationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_location_endpoint(
    location_data: LocationCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LocationResponse:

    try:
        location = await create_location(
            db,
            location_data,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return location

@router.get(
    "/{location_id}",
    response_model=LocationResponse,
)
async def get_location_endpoint(
    location_id: int,
    db:Annotated[AsyncSession, Depends(get_db)],
) -> LocationResponse:

    location = await get_location(
        db,
        location_id,
    )
    if location is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="location not found",
        )
    return location

@router.patch(
    "/{location_id}",
    response_model=LocationResponse,
)
async def update_location_endpoint(
    location_id: int,
    location_data: LocationUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LocationResponse:

    location = await get_location(
        db,
        location_id,
    )
    if location is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="location noot found",
        )
    try:
        new_location = await update_location(
            db,
            location,
            location_data,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    
    return new_location