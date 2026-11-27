"""Explicitly enabled reset of disposable development business data."""

import re
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.authorization import AdminUser
from app.core.config import settings
from app.core.database import Base, get_db
from app.models import User

router = APIRouter(prefix="/development", tags=["Development"])


def enabled() -> bool:
    return settings.app_environment == "development" and settings.enable_dev_reset


class ResetRequest(BaseModel):
    confirmation: Literal["CLEAR DEVELOPMENT DATA"]


class ResetResponse(BaseModel):
    cleared: bool
    photos_removed: int
    photo_cleanup_complete: bool


@router.get("/reset-status")
async def reset_status(user: AdminUser) -> dict[str, bool]:
    return {"enabled": enabled()}


def photo_snapshot() -> tuple[list[Path], bool]:
    directory = Path(settings.item_image_dir)
    try:
        return [p for p in directory.iterdir() if re.fullmatch(r"[0-9a-f]{32}\.jpg", p.name)], True
    except FileNotFoundError:
        return [], True
    except OSError:
        return [], False


def remove_photos(paths: list[Path]) -> tuple[int, bool]:
    removed, complete = 0, True
    for path in paths:
        try:
            path.unlink(missing_ok=True)
            removed += 1
        except OSError:
            complete = False
    return removed, complete


@router.post("/reset", response_model=ResetResponse)
async def reset_business_data(
    data: ResetRequest, db: Annotated[AsyncSession, Depends(get_db)], user: AdminUser
):
    if not enabled():
        raise HTTPException(404, "Development reset is disabled")
    paths, scanned = await run_in_threadpool(photo_snapshot)
    # Use registered business tables only; keep users, Alembic and other schemas.
    # No CASCADE: an unexpected external FK must block the reset, not delete data.
    preparer = db.bind.dialect.identifier_preparer
    tables = [table for table in Base.metadata.sorted_tables if table is not User.__table__]
    names = ", ".join(preparer.format_table(table) for table in tables)
    try:
        await db.execute(text("SET LOCAL lock_timeout = '5s'"))
        await db.execute(text(f"TRUNCATE TABLE {names} RESTART IDENTITY"))
        await db.commit()
    except DBAPIError as error:
        await db.rollback()
        raise HTTPException(409, "Reset could not finish; stop other activity and retry") from error
    # Cleanup only known generated files after successful DB commit. Never recurse
    # through the configured storage directory or remove unrelated files.
    removed, cleaned = await run_in_threadpool(remove_photos, paths)
    return {
        "cleared": True,
        "photos_removed": removed,
        "photo_cleanup_complete": scanned and cleaned,
    }
