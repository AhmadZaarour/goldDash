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


def test_database_pooling_defaults_on_and_can_be_disabled(monkeypatch):
    monkeypatch.delenv("DATABASE_POOLING", raising=False)
    assert runtime_settings().database_pooling is True
    monkeypatch.setenv("DATABASE_POOLING", "false")
    assert runtime_settings().database_pooling is False
