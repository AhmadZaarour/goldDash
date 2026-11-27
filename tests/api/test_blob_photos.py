import io
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx2
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
def private_store(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "item_image_storage", "vercel_blob")
    monkeypatch.setattr(settings, "item_image_dir", str(tmp_path))
    objects = {}

    async def put(key, body, **options):
        assert options == {
            "access": "private",
            "content_type": "image/jpeg",
            "add_random_suffix": False,
            "allow_overwrite": False,
        }
        objects[key] = body

    async def get(key, **options):
        assert options == {"access": "private"}
        if key not in objects:
            raise photo_storage.blob.BlobNotFoundError()
        return SimpleNamespace(body=objects[key])

    async def delete(key):
        objects.pop(key, None)

    monkeypatch.setattr(photo_storage.blob, "put_blob", AsyncMock(side_effect=put))
    monkeypatch.setattr(photo_storage.blob, "get_blob", AsyncMock(side_effect=get))
    monkeypatch.setattr(photo_storage.blob, "delete_blob", AsyncMock(side_effect=delete))
    return objects


async def test_private_photo_preserves_normalization_and_workspace_authorization(
    client, test_session_factory, private_store, tmp_path
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
    assert len(private_store) == 1
    assert not list(tmp_path.iterdir())
    reads = photo_storage.blob.get_blob.call_count
    assert (await client.get(url, headers={"Authorization": ""})).status_code == 401
    other_user = await headers_for(test_session_factory, "cashier")
    assert (await client.get(url, headers=other_user)).status_code == 404
    assert (await client.get(url, headers={"X-Business-Unit": "factory"})).status_code == 404
    assert photo_storage.blob.get_blob.call_count == reads


async def test_private_photo_expiry_removes_only_unattached_uploads(
    client, test_session_factory, private_store
):
    first = await client.post("/api/v1/purchases/photos", content=jpeg())
    async with test_session_factory() as db:
        upload = await db.scalar(
            select(PhotoUpload).where(PhotoUpload.token == first.json()["token"])
        )
        upload.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()
    assert (await client.get(first.json()["image_url"])).status_code == 404
    second = await client.post("/api/v1/purchases/photos", content=jpeg())
    assert second.status_code == 201
    assert len(private_store) == 1
    assert (await client.get(second.json()["image_url"])).status_code == 200
    photo_storage.blob.delete_blob.assert_awaited_once()


async def test_cloud_upload_failure_is_sanitized(client, private_store):
    photo_storage.blob.put_blob.side_effect = photo_storage.blob.BlobAccessError("secret details")
    response = await client.post("/api/v1/purchases/photos", content=jpeg())
    assert response.status_code == 503
    assert response.json() == {"detail": "Photo storage is temporarily unavailable"}


async def test_database_failure_discards_uploaded_blob(client, private_store, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession

    async def fail_commit(self):
        raise RuntimeError("Simulated database failure")

    monkeypatch.setattr(AsyncSession, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="Simulated database failure"):
        await client.post("/api/v1/purchases/photos", content=jpeg())
    assert private_store == {}
    photo_storage.blob.delete_blob.assert_awaited_once()


async def test_cleanup_outage_does_not_hide_transaction_error(private_store, monkeypatch):
    monkeypatch.setattr(
        item_photos_service,
        "delete_photo",
        AsyncMock(side_effect=HTTPException(503, "storage unavailable")),
    )
    await item_photos_service.discard_photo("a" * 32 + ".jpg")


async def test_vercel_rejects_oversized_images_before_storage(client, private_store, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    response = await client.post("/api/v1/purchases/photos", content=b"x" * (4 * 1024 * 1024 + 1))
    assert response.status_code == 413
    assert private_store == {}
    photo_storage.blob.put_blob.assert_not_awaited()


async def test_storage_reads_distinguish_missing_objects_from_outages(private_store):
    filename = "a" * 32 + ".jpg"
    with pytest.raises(HTTPException) as missing:
        await photo_storage.read_photo(filename)
    assert missing.value.status_code == 404
    photo_storage.blob.get_blob.side_effect = photo_storage.blob.BlobAccessError("secret")
    with pytest.raises(HTTPException) as unavailable:
        await photo_storage.read_photo(filename)
    assert unavailable.value.status_code == 503
    assert "secret" not in unavailable.value.detail


async def test_cloud_reset_is_disabled_even_in_development(client, private_store, monkeypatch):
    monkeypatch.setattr(settings, "app_environment", "development")
    monkeypatch.setattr(settings, "enable_dev_reset", True)
    assert (await client.get("/api/v1/development/reset-status")).json() == {"enabled": False}
    response = await client.post(
        "/api/v1/development/reset", json={"confirmation": "CLEAR DEVELOPMENT DATA"}
    )
    assert response.status_code == 404


async def test_storage_round_trip_uses_installed_sdk_with_authenticated_private_requests(
    monkeypatch, tmp_path
):
    from vercel.api import session

    filename = "a" * 32 + ".jpg"
    key = f"items/{filename}"
    url = f"https://demostore.private.blob.vercel-storage.com/{key}"
    data = jpeg()
    credential = f"vercel_blob_rw_demostore_{uuid4().hex}"
    requests = []

    def handle(request):
        requests.append(request)
        assert request.headers["authorization"] == f"Bearer {credential}"
        if request.method == "PUT":
            assert request.url.params["pathname"] == key
            assert request.headers["x-vercel-blob-access"] == "private"
            assert request.headers["x-allow-overwrite"] == "0"
            assert request.content == data
            return httpx2.Response(
                200,
                json={
                    "url": url,
                    "downloadUrl": url,
                    "pathname": key,
                    "contentType": "image/jpeg",
                    "contentDisposition": "inline",
                    "etag": "test",
                },
            )
        if request.method == "GET":
            assert str(request.url) == url
            return httpx2.Response(200, content=data, headers={"Content-Type": "image/jpeg"})
        assert request.method == "POST"
        assert request.url.path == "/api/blob/delete"
        assert json.loads(request.content) == {"urls": [key]}
        return httpx2.Response(200, json={})

    def sdk_session():
        return session(
            service_options=[
                photo_storage.blob.BlobServiceOptions(
                    credentials_factory=lambda: photo_storage.blob.BlobCredentials(
                        token=credential, store_id="demostore"
                    )
                )
            ],
            httpx_client_factory=lambda: httpx2.AsyncClient(transport=httpx2.MockTransport(handle)),
        )

    monkeypatch.setattr(settings, "item_image_storage", "vercel_blob")
    monkeypatch.setattr(settings, "item_image_dir", str(tmp_path))
    monkeypatch.setattr(photo_storage, "session", sdk_session)
    await photo_storage.write_photo(filename, data)
    assert await photo_storage.read_photo(filename) == data
    await photo_storage.delete_photo(filename)
    assert [request.method for request in requests] == ["PUT", "GET", "POST"]
    assert not list(tmp_path.iterdir())
