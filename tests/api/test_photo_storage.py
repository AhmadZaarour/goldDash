import io
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from PIL import Image
from sqlalchemy import select

from app.core.config import settings
from app.models.photoUpload import PhotoUpload
from app.services import item_photos_service, photo_storage
from tests.api.test_backend_access import headers_for
from tests.api.test_item_photos import jpeg

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.fixture
def photo_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "item_image_dir", str(tmp_path))
    return tmp_path


async def test_staged_photo_preserves_normalization_and_workspace_authorization(
    client, test_session_factory, photo_directory
):
    uploaded = await client.post("/api/v1/purchases/photos", content=jpeg())
    assert uploaded.status_code == 201, uploaded.text
    url = uploaded.json()["image_url"]
    assert url.startswith("/api/v1/media/items/")
    fetched = await client.get(url)
    assert fetched.status_code == 200
    assert fetched.headers["cache-control"] == "private, no-store"
    assert fetched.headers["x-content-type-options"] == "nosniff"
    with Image.open(io.BytesIO(fetched.content)) as normalized:
        assert normalized.width == 2048
        assert not normalized.getexif()
    assert len(list(photo_directory.glob("*.jpg"))) == 1
    assert (await client.get(url, headers={"Authorization": ""})).status_code == 401
    other_user = await headers_for(test_session_factory, "cashier")
    assert (await client.get(url, headers=other_user)).status_code == 404
    assert (await client.get(url, headers={"X-Business-Unit": "factory"})).status_code == 404


async def test_expired_staged_photo_is_removed_on_next_upload(
    client, test_session_factory, photo_directory
):
    first = await client.post("/api/v1/purchases/photos", content=jpeg())
    first_file = photo_directory / first.json()["image_url"].rsplit("/", 1)[-1]
    async with test_session_factory() as db:
        upload = await db.scalar(
            select(PhotoUpload).where(PhotoUpload.token == first.json()["token"])
        )
        upload.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()
    assert (await client.get(first.json()["image_url"])).status_code == 404
    second = await client.post("/api/v1/purchases/photos", content=jpeg())
    assert second.status_code == 201, second.text
    assert not first_file.exists()
    assert len(list(photo_directory.glob("*.jpg"))) == 1
    assert (await client.get(second.json()["image_url"])).status_code == 200


async def test_upload_storage_failure_is_sanitized(client, photo_directory, monkeypatch):
    def unavailable(self, data):
        raise OSError("private filesystem details")

    monkeypatch.setattr(Path, "write_bytes", unavailable)
    response = await client.post("/api/v1/purchases/photos", content=jpeg())
    assert response.status_code == 503
    assert response.json() == {"detail": "Photo storage is temporarily unavailable"}
    assert not list(photo_directory.iterdir())


async def test_database_failure_discards_uploaded_photo(client, photo_directory, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession

    async def fail_commit(self):
        raise RuntimeError("Simulated database failure")

    monkeypatch.setattr(AsyncSession, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="Simulated database failure"):
        await client.post("/api/v1/purchases/photos", content=jpeg())
    assert not list(photo_directory.iterdir())


async def test_cleanup_outage_is_reported_without_raising(monkeypatch, caplog):
    monkeypatch.setattr(
        item_photos_service,
        "delete_photo",
        AsyncMock(side_effect=HTTPException(503, "storage unavailable")),
    )
    await item_photos_service.discard_photo("a" * 32 + ".jpg")
    assert "Could not clean up unattached item photo" in caplog.text


async def test_storage_reads_distinguish_missing_files_from_outages(
    photo_directory, monkeypatch
):
    filename = "a" * 32 + ".jpg"
    with pytest.raises(HTTPException) as missing:
        await photo_storage.read_photo(filename)
    assert missing.value.status_code == 404

    def unavailable(self):
        raise PermissionError("private filesystem details")

    monkeypatch.setattr(Path, "read_bytes", unavailable)
    with pytest.raises(HTTPException) as failed:
        await photo_storage.read_photo(filename)
    assert failed.value.status_code == 503
    assert failed.value.detail == "Photo storage is temporarily unavailable"


async def test_staged_upload_accepts_a_photo_between_five_and_ten_mib(client, photo_directory):
    data = jpeg() + b"\0" * (5 * 1024 * 1024)
    response = await client.post("/api/v1/purchases/photos", content=data)
    assert response.status_code == 201, response.text
    assert (await client.get(response.json()["image_url"])).status_code == 200


async def test_storage_rejects_paths_outside_the_image_directory(photo_directory):
    for operation in (
        lambda: photo_storage.write_photo("../outside.jpg", b"invalid"),
        lambda: photo_storage.read_photo("../outside.jpg"),
        lambda: photo_storage.delete_photo("../outside.jpg"),
    ):
        with pytest.raises(HTTPException) as invalid:
            await operation()
        assert invalid.value.status_code == 404
    assert not list(photo_directory.iterdir())
