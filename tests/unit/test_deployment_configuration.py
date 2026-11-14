from secrets import token_hex

from app.core.config import Settings


def runtime_settings():
    return Settings(
        _env_file=None,
        database_url="postgresql+psycopg://example.invalid/shop",
        secret_key=token_hex(32),
    )


def test_runtime_does_not_require_a_test_database(monkeypatch):
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    config = runtime_settings()
    assert config.test_database_url is None


def test_vercel_uses_persistent_photos_and_no_process_database_pool(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("ITEM_IMAGE_STORAGE", raising=False)
    monkeypatch.delenv("DATABASE_POOLING", raising=False)
    config = runtime_settings()
    assert config.item_image_storage == "vercel_blob"
    assert config.database_pooling is False


def test_local_defaults_and_explicit_storage_configuration(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("ITEM_IMAGE_STORAGE", raising=False)
    monkeypatch.delenv("DATABASE_POOLING", raising=False)
    config = runtime_settings()
    assert config.item_image_storage == "local"
    assert config.database_pooling is True
    monkeypatch.setenv("ITEM_IMAGE_STORAGE", "vercel_blob")
    assert runtime_settings().item_image_storage == "vercel_blob"
