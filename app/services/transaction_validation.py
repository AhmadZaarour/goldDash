"""Validate active trading entities before changing inventory or money."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.location import Location
from app.models.suppliers import Supplier


async def require_active_location(db: AsyncSession, location_id: int) -> Location:
    location = await db.scalar(
        select(Location)
        .where(Location.id == location_id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    if location is None:
        raise ValueError("Location does not exist")
    if not location.is_active:
        raise ValueError("Location is inactive")
    return location


async def require_active_supplier(db: AsyncSession, supplier_id: int) -> Supplier:
    supplier = await db.scalar(
        select(Supplier)
        .where(Supplier.id == supplier_id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    if supplier is None:
        raise ValueError("Supplier does not exist")
    if not supplier.is_active:
        raise ValueError("Supplier is inactive")
    return supplier
