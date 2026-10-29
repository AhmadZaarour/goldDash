import pytest
from sqlalchemy import func, select, text

from app.api.v1 import development
from app.core.config import settings
from app.core.database import Base
from app.models import Product, User
from tests.api.test_auth import login_user
from tests.api.test_backend_access import headers_for
from tests.api.test_purchase import test_create_purchase as make_purchase

pytestmark = pytest.mark.asyncio(loop_scope="session")
URL = "/api/v1/development/reset"
PAYLOAD = {"confirmation": "CLEAR DEVELOPMENT DATA"}


@pytest.mark.parametrize(
    "environment,flag", [("production", True), ("test", True), ("development", False)]
)
async def test_reset_is_disabled_outside_explicit_development(
    client, test_session_factory, monkeypatch, environment, flag
):
    await make_purchase(client, test_session_factory)
    monkeypatch.setattr(settings, "app_environment", environment)
    monkeypatch.setattr(settings, "enable_dev_reset", flag)
    assert (await client.get(URL + "-status")).json() == {"enabled": False}
    assert (await client.post(URL, json=PAYLOAD)).status_code == 404
    async with test_session_factory() as db:
        assert await db.scalar(select(func.count()).select_from(Product)) == 1


async def test_reset_requires_admin_and_exact_confirmation(
    client, test_session_factory, monkeypatch
):
    monkeypatch.setattr(settings, "app_environment", "development")
    monkeypatch.setattr(settings, "enable_dev_reset", True)
    assert (await client.get(URL + "-status")).json() == {"enabled": True}
    for role in ["cashier", "employee"]:
        headers = await headers_for(test_session_factory, role)
        assert (await client.post(URL, json=PAYLOAD, headers=headers)).status_code == 403
        assert (await client.get(URL + "-status", headers=headers)).status_code == 403
    assert (await client.post(URL, json=PAYLOAD, headers={"Authorization": ""})).status_code == 401
    for phrase in ["", "clear development data", "CLEAR DEVELOPMENT DATA "]:
        assert (await client.post(URL, json={"confirmation": phrase})).status_code == 422


async def test_reset_clears_business_data_and_photos_preserving_accounts_and_schema(
    client, test_session_factory, monkeypatch, tmp_path
):
    await make_purchase(client, test_session_factory)
    tokens = await login_user(client)
    photo = tmp_path / ("a" * 32 + ".jpg")
    photo.write_bytes(b"development photo")
    unrelated = tmp_path / "keep.txt"
    unrelated.write_text("unrelated storage file")
    nested = tmp_path / "unrelated-folder"
    nested.mkdir()
    monkeypatch.setattr(settings, "app_environment", "development")
    monkeypatch.setattr(settings, "enable_dev_reset", True)
    monkeypatch.setattr(settings, "item_image_dir", str(tmp_path))
    async with test_session_factory() as db:
        users_before = await db.scalar(select(func.count()).select_from(User))
        version_before = await db.scalar(text("SELECT version_num FROM alembic_version"))
    result = await client.post(URL, json=PAYLOAD)
    assert result.status_code == 200, result.text
    assert result.json() == {"cleared": True, "photos_removed": 1, "photo_cleanup_complete": True}
    assert not photo.exists()
    assert unrelated.exists() and nested.is_dir()
    async with test_session_factory() as db:
        for table in Base.metadata.sorted_tables:
            count = await db.scalar(select(func.count()).select_from(table))
            assert count == (users_before if table is User.__table__ else 0), table.name
        assert await db.scalar(text("SELECT version_num FROM alembic_version")) == version_before
    # Existing authentication and refresh sessions continue to work.
    assert (
        await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
        )
    ).status_code == 200
    assert (
        await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    ).status_code == 200
    # A fresh purchase works with the preserved schema/accounts after identity reset.
    await make_purchase(client, test_session_factory)


async def test_reset_does_not_cascade_into_unknown_tables_or_remove_photos_on_failure(
    client, test_session_factory, monkeypatch, tmp_path
):
    await make_purchase(client, test_session_factory)
    monkeypatch.setattr(settings, "app_environment", "development")
    monkeypatch.setattr(settings, "enable_dev_reset", True)
    monkeypatch.setattr(settings, "item_image_dir", str(tmp_path))
    photo = tmp_path / ("b" * 32 + ".jpg")
    photo.write_bytes(b"preserve on database failure")
    async with test_session_factory() as db:
        await db.execute(
            text("CREATE TABLE dev_reset_test_blocker (product_id INTEGER REFERENCES products(id))")
        )
        await db.commit()
    try:
        response = await client.post(URL, json=PAYLOAD)
        assert response.status_code == 409
        assert photo.exists()
        async with test_session_factory() as db:
            assert await db.scalar(select(func.count()).select_from(Product)) == 1
    finally:
        async with test_session_factory() as db:
            await db.execute(text("DROP TABLE dev_reset_test_blocker"))
            await db.commit()


async def test_reset_reports_photo_cleanup_failure(client, monkeypatch):
    monkeypatch.setattr(settings, "app_environment", "development")
    monkeypatch.setattr(settings, "enable_dev_reset", True)
    monkeypatch.setattr(development, "photo_snapshot", lambda: ([], False))
    result = await client.post(URL, json=PAYLOAD)
    assert result.status_code == 200
    assert result.json()["cleared"] is True
    assert result.json()["photo_cleanup_complete"] is False


async def test_photo_helpers_handle_missing_storage_and_unlink_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "item_image_dir", str(tmp_path / "absent"))
    assert development.photo_snapshot() == ([], True)
    # A directory named like a generated image must never be recursively removed.
    directory = tmp_path / ("c" * 32 + ".jpg")
    directory.mkdir()
    assert development.remove_photos([directory]) == (0, False)
    assert directory.is_dir()
