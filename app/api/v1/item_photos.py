"""Authenticated, locally persisted item photos; no third-party storage required."""

import asyncio
import io
import re
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from PIL import Image, ImageOps, UnidentifiedImageError

from app.api.v1.inventory_operations import Database
from app.core.authorization import CashierUser
from app.core.config import settings
from app.core.dependencies import CurrentUser
from app.models.inventoryItem import InventoryItem
from app.schemas.inventory import InventoryItemResponse

router = APIRouter(tags=["Item photos"])
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


@router.post("/inventory/items/{item_id}/photo", response_model=InventoryItemResponse)
async def upload_photo(item_id: int, request: Request, db: Database, user: CashierUser):
    item = await db.get(InventoryItem, item_id)
    if item is None:
        raise HTTPException(404, "Item not found")
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > LIMIT:
            raise HTTPException(413, "Photo must be smaller than 10 MB")
    filename = await asyncio.to_thread(save_photo, bytes(data))
    item.image_url = str(request.url_for("read_item_photo", filename=filename))
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        await asyncio.to_thread((Path(settings.item_image_dir) / filename).unlink, missing_ok=True)
        raise
    await db.refresh(item)
    return item


@router.get("/media/items/{filename}", name="read_item_photo")
async def read_item_photo(filename: str, user: CurrentUser):
    if not re.fullmatch(r"[a-f0-9]{32}\.jpg", filename):
        raise HTTPException(404, "Photo not found")
    path = Path(settings.item_image_dir) / filename
    if not await asyncio.to_thread(path.is_file):
        raise HTTPException(404, "Photo not found")
    return FileResponse(
        path,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )
