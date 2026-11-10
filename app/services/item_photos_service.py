import asyncio
import io
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, HTTPException, Request
from fastapi.responses import FileResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select

from app.api.v1.inventory_operations import Database
from app.core.config import settings
from app.core.dependencies import CurrentUser
from app.core.workspace import active_unit
from app.models.inventoryItem import InventoryItem
from app.models.photoUpload import PhotoUpload
from app.models.user import User

LIMIT = 10 * 1024 * 1024

def save_photo(data: bytes) -> str:
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.format not in {"JPEG", "PNG", "WEBP"}:
                raise HTTPException(415, "Choose a JPEG, PNG or WebP photo")
            if source.width * source.height > 20_000_000:
                raise HTTPException(413, "Photo dimensions are too large")
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((2048, 2048))
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=85)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as error:
        raise HTTPException(422, "Invalid or unsupported photo") from error
    root = Path(settings.item_image_dir)
    root.mkdir(parents=True, exist_ok=True)
    filename = uuid4().hex + ".jpg"
    (root / filename).write_bytes(output.getvalue())
    return filename


async def receive_photo(request: Request) -> str:
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > LIMIT:
            raise HTTPException(413, "Photo must be smaller than 10 MB")
    filename = await asyncio.to_thread(save_photo, bytes(data))
    return filename


async def photo_user(user: CurrentUser) -> User:
    if user.role not in {"admin", "cashier"} and not (
        active_unit() == "factory" and user.role == "employee"
    ):
        raise HTTPException(403, "Insufficient permissions")
    return user


PhotoUser = Annotated[User, Depends(photo_user)]

async def stage_photo_service(request: Request, db: Database, user: PhotoUser) -> dict[str, str]:
    # Lock expired rows so cleanup cannot race purchase attachment or another cleanup.
    expired = await db.scalars(
        select(PhotoUpload)
        .where(PhotoUpload.inventory_item_id.is_(None), PhotoUpload.expires_at < datetime.now(UTC))
        .limit(100)
        .with_for_update(skip_locked=True)
    )
    old_files = []
    for upload in expired:
        old_files.append(upload.filename)
        await db.delete(upload)
    filename = await receive_photo(request)
    token = uuid4().hex
    db.add(
        PhotoUpload(
            token=token,
            filename=filename,
            created_by=user.id,
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
    )
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        await asyncio.to_thread((Path(settings.item_image_dir) / filename).unlink, missing_ok=True)
        raise
    for old in old_files:
        await asyncio.to_thread((Path(settings.item_image_dir) / old).unlink, missing_ok=True)
    return {"token": token, "image_url": f"/api/v1/media/items/{filename}"}


async def upload_photo_service(item_id: int, request: Request, db: Database, user: PhotoUser) -> InventoryItem:
    item = await db.get(InventoryItem, item_id)
    if item is None:
        raise HTTPException(404, "Item not found")
    filename = await receive_photo(request)
    item.image_url = str(request.url_for("read_item_photo", filename=filename))
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        await asyncio.to_thread((Path(settings.item_image_dir) / filename).unlink, missing_ok=True)
        raise
    await db.refresh(item)
    return item


async def read_item_photo_service(filename: str, user: CurrentUser, db: Database) -> FileResponse:
    if not re.fullmatch(r"[a-f0-9]{32}\.jpg", filename):
        raise HTTPException(404, "Photo not found")
    owned = await db.scalar(
        select(InventoryItem.id).where(InventoryItem.image_url.endswith("/" + filename)).limit(1)
    )
    staged = await db.scalar(
        select(PhotoUpload.token)
        .where(
            PhotoUpload.filename == filename,
            PhotoUpload.created_by == user.id,
            PhotoUpload.inventory_item_id.is_(None),
        )
        .limit(1)
    )
    if owned is None and staged is None:
        raise HTTPException(404, "Photo not found")
    path = Path(settings.item_image_dir) / filename
    if not await asyncio.to_thread(path.is_file):
        raise HTTPException(404, "Photo not found")
    return FileResponse(
        path,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )