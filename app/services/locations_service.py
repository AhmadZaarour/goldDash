from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.locations import LocationCreate, LocationUpdate
from app.models.location import Location

async def create_location(
    db: AsyncSession,
    location_data: LocationCreate,
) -> Location:

    existing_location = await db.scalar(
        select(Location).where(
            Location.name == location_data.name,
        )
    )

    if existing_location is not None:
        raise ValueError("Location already exists")

    location = Location(
        name=location_data.name,
        code=location_data.code,
        address=location_data.address,
    )

    db.add(location)

    await db.commit()
    await db.refresh(location)

    return location

async def get_locations(
        db: AsyncSession,
) -> list[Location]:

    locations = await db.scalars(
        select(Location).order_by(Location.id)
    )

    return list(locations.all())

async def get_location(
    db: AsyncSession,
    location_id: int,
) -> Location | None:

    return await db.scalar(
        select(Location).where(
            Location.id == location_id,
        )
    )

async def update_location(
    db: AsyncSession,
    location: Location,
    location_data: LocationUpdate,
) -> Location:

    update_data = location_data.model_dump(
        exclude_unset=True,
    )

    if "name" in update_data:
        existing_location = await db.scalar(
            select(Location).where(
                Location.name == update_data["name"],
                Location.id != location.id,
            )
        )

        if existing_location is not None:
            raise ValueError("location already exists")

    for field, value in update_data.items():
        setattr(location, field, value)

    await db.commit()
    await db.refresh(location)

    return location