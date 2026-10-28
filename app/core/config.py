from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Gold Shop API"
    app_version: str = "0.1.0"
    debug: bool = False
    cors_origins: list[str] = []

    database_url: str
    test_database_url: str

    redis_url: str = "redis://localhost:6379/0"
    test_redis_url: str = "redis://localhost:6379/1"

    algorithm: str = "HS256"

    secret_key: str
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
