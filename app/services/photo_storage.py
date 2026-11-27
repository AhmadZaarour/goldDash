"""Persist normalized photos in the configured local image directory."""

import asyncio
import re
from pathlib import Path

from fastapi import HTTPException

from app.core.config import settings


def _path(filename: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}\.jpg", filename):
        raise HTTPException(404, "Photo not found")
    return Path(settings.item_image_dir) / filename


async def write_photo(filename: str, data: bytes) -> None:
    path = _path(filename)
    try:
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)
    except OSError as error:
        raise HTTPException(503, "Photo storage is temporarily unavailable") from error


async def read_photo(filename: str) -> bytes:
    path = _path(filename)
    try:
        return await asyncio.to_thread(path.read_bytes)
    except FileNotFoundError as error:
        raise HTTPException(404, "Photo not found") from error
    except OSError as error:
        raise HTTPException(503, "Photo storage is temporarily unavailable") from error


async def delete_photo(filename: str) -> None:
    path = _path(filename)
    try:
        await asyncio.to_thread(path.unlink, missing_ok=True)
    except OSError as error:
        raise HTTPException(503, "Photo storage is temporarily unavailable") from error
