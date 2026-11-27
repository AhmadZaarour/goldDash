"""Remove unused records through explicitly authorized resource endpoints."""

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base


async def remove_unused_record(
    db: AsyncSession, model: type[Base], record_id: int, label: str
) -> None:
    table = model.__table__
    removed = await db.scalar(delete(table).where(table.c.id == record_id).returning(table.c.id))
    if removed is None:
        raise HTTPException(404, f"{label} not found")
    # The database restricts deletion as soon as any transaction references the record.
    await db.commit()


async def is_referenced(db: AsyncSession, model: type[Base], record_id: int) -> bool:
    primary_key = model.__table__.c.id
    for table in Base.metadata.tables.values():
        for foreign_key in table.foreign_keys:
            if foreign_key.column is primary_key:
                statement = select(foreign_key.parent).where(foreign_key.parent == record_id)
                if await db.scalar(statement.limit(1)) is not None:
                    return True
    return False
