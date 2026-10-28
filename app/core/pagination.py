"""Bounded array responses with pagination metadata in HTTP headers."""

from fastapi import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def paginate(db: AsyncSession, statement, response: Response, limit: int, offset: int):
    total = await db.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Limit"] = str(limit)
    response.headers["X-Offset"] = str(offset)
    return list(await db.scalars(statement.limit(limit).offset(offset)))
