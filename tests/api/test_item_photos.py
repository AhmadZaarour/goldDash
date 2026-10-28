import asyncio
import io

import pytest
from PIL import Image

from app.core.config import settings
from tests.api.test_backend_access import headers_for
from tests.api.test_purchase import test_create_purchase as create_purchase

pytestmark = pytest.mark.asyncio(loop_scope="session")


def jpeg():
    output = io.BytesIO()
    image = Image.new("RGB", (2500, 1000), "#c8a558")
    exif = Image.Exif()
    exif[270] = "Private camera metadata"
    image.save(output, "JPEG", exif=exif)
    return output.getvalue()


async def test_phone_photo_persists_normalized_image_and_requires_auth(
    client, test_session_factory, tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "item_image_dir", str(tmp_path))
    _, _, inventory = await create_purchase(client, test_session_factory)
    item_id = inventory.json()["id"]
    cashier = await headers_for(test_session_factory, "cashier")
    response = await client.post(
        f"/api/v1/inventory/items/{item_id}/photo",
        content=jpeg(),
        headers={**cashier, "Content-Type": "image/jpeg"},
    )
    assert response.status_code == 200, response.text
    url = response.json()["image_url"]
    assert url.startswith("http://test/api/v1/media/items/")
    fetched = await client.get(url)
    assert fetched.status_code == 200
    assert fetched.headers["content-type"] == "image/jpeg"
    with Image.open(io.BytesIO(fetched.content)) as normalized:
        assert normalized.width == 2048
        assert not normalized.getexif()
    files = await asyncio.to_thread(lambda: list(tmp_path.glob("*.jpg")))
    assert len(files) == 1
    assert (await client.get(url, headers={"Authorization": ""})).status_code == 401
    employee = await headers_for(test_session_factory, "employee")
    assert (
        await client.post(
            f"/api/v1/inventory/items/{item_id}/photo", content=jpeg(), headers=employee
        )
    ).status_code == 403
    assert (await client.get(f"/api/v1/inventory/items/{item_id}")).json()["image_url"] == url


async def test_invalid_photos_do_not_change_item_or_write_files(
    client, test_session_factory, tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "item_image_dir", str(tmp_path))
    _, _, inventory = await create_purchase(client, test_session_factory)
    url = f"/api/v1/inventory/items/{inventory.json()['id']}/photo"
    assert (await client.post(url, content=b'<svg onload="alert(1)"></svg>')).status_code == 422
    assert (await client.post(url, content=b"x" * (10 * 1024 * 1024 + 1))).status_code == 413
    assert (await client.get("/api/v1/media/items/not-a-photo.jpg")).status_code == 404
    assert list(tmp_path.iterdir()) == []
