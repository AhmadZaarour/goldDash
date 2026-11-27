import asyncio
import io
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, HTTPException, Request
from fastapi.responses import Response
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import select

from app.api.v1.inventory_operations import Database
from app.core.dependencies import CurrentUser
from app.core.workspace import active_unit
from app.models.inventoryItem import InventoryItem
from app.models.photoUpload import PhotoUpload
from app.models.user import User
from app.services.photo_storage import delete_photo, read_photo, write_photo

LIMIT = 10 * 1024 * 1024
logger = logging.getLogger(__name__)


def normalize_photo(data: bytes) -> bytes:
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
    return output.getvalue()


async def receive_photo(request: Request) -> str:
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > LIMIT:
            raise HTTPException(413, "Photo must be smaller than 10 MB")
    normalized = await asyncio.to_thread(normalize_photo, bytes(data))
    filename = uuid4().hex + ".jpg"
    await write_photo(filename, normalized)
    return filename


async def discard_photo(filename: str) -> None:
    # A cleanup outage must not hide a database error or turn a committed upload
    # into a failed request that the user will retry.
    try:
        await delete_photo(filename)
    except HTTPException:
        logger.warning("Could not clean up unattached item photo %s", filename)


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
        await discard_photo(filename)
        raise
    for old in old_files:
        await discard_photo(old)
    return {"token": token, "image_url": f"/api/v1/media/items/{filename}"}


async def upload_photo_service(
    item_id: int, request: Request, db: Database, user: PhotoUser
) -> InventoryItem:
    item = await db.get(InventoryItem, item_id)
    if item is None:
        raise HTTPException(404, "Item not found")
    filename = await receive_photo(request)
    item.image_url = str(request.url_for("read_item_photo", filename=filename))
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        await discard_photo(filename)
        raise
    await db.refresh(item)
    return item


async def read_item_photo_service(filename: str, user: CurrentUser, db: Database) -> Response:
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
            PhotoUpload.expires_at > datetime.now(UTC),
        )
        .limit(1)
    )
    if owned is None and staged is None:
        raise HTTPException(404, "Photo not found")
    return Response(
        await read_photo(filename),
        media_type="image/jpeg",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )
