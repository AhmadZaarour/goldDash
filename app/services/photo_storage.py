"""Persist normalized photos without exposing object-store URLs or credentials."""

import asyncio
import re
from pathlib import Path

from fastapi import HTTPException
from httpx2 import HTTPError
from vercel import blob
from vercel.api import session

from app.core.config import settings


def _key(filename: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{32}\.jpg", filename):
        raise HTTPException(404, "Photo not found")
    return f"items/{filename}"


async def write_photo(filename: str, data: bytes) -> None:
    key = _key(filename)
    try:
        if settings.item_image_storage == "vercel_blob":
            async with session():
                await blob.put_blob(
                    key,
                    data,
                    access="private",
                    content_type="image/jpeg",
                    add_random_suffix=False,
                    allow_overwrite=False,
                )
        else:

            def write_local():
                root = Path(settings.item_image_dir)
                root.mkdir(parents=True, exist_ok=True)
                (root / filename).write_bytes(data)

            await asyncio.to_thread(write_local)
    except (blob.BlobError, HTTPError, OSError) as error:
        raise HTTPException(503, "Photo storage is temporarily unavailable") from error


async def read_photo(filename: str) -> bytes:
    key = _key(filename)
    try:
        if settings.item_image_storage == "vercel_blob":
            async with session():
                result = await blob.get_blob(key, access="private")
                return result.body
        return await asyncio.to_thread((Path(settings.item_image_dir) / filename).read_bytes)
    except (blob.BlobNotFoundError, FileNotFoundError) as error:
        raise HTTPException(404, "Photo not found") from error
    except (blob.BlobError, HTTPError, OSError) as error:
        raise HTTPException(503, "Photo storage is temporarily unavailable") from error


async def delete_photo(filename: str) -> None:
    key = _key(filename)
    try:
        if settings.item_image_storage == "vercel_blob":
            async with session():
                await blob.delete_blob(key)
        else:
            await asyncio.to_thread(
                (Path(settings.item_image_dir) / filename).unlink, missing_ok=True
            )
    except blob.BlobNotFoundError:
        pass
    except (blob.BlobError, HTTPError, OSError) as error:
        raise HTTPException(503, "Photo storage is temporarily unavailable") from error
