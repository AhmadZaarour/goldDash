import asyncio
import os
import subprocess
from collections.abc import AsyncGenerator
from pathlib import Path
from uuid import uuid4

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.user import User
from app.services import session_service

PROJECT_ROOT = Path(__file__).resolve().parents[1]

TEST_DATABASE_URL = settings.test_database_url
TEST_REDIS_URL = settings.test_redis_url


def _validate_test_configuration() -> None:
    if not TEST_DATABASE_URL or "test" not in TEST_DATABASE_URL.lower():
        raise RuntimeError(
            "TEST_DATABASE_URL must be configured with a database name containing 'test'."
        )
    if TEST_DATABASE_URL == settings.database_url:
        raise RuntimeError("TEST_DATABASE_URL must differ from DATABASE_URL.")
    if not TEST_REDIS_URL:
        raise RuntimeError("TEST_REDIS_URL must be configured.")
    if TEST_REDIS_URL == settings.redis_url:
        raise RuntimeError("TEST_REDIS_URL must differ from REDIS_URL.")


_validate_test_configuration()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def test_engine() -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
    )

    # Exercise the same migrations used to deploy the application.
    migration_env = dict(os.environ, DATABASE_URL=TEST_DATABASE_URL)
    await asyncio.to_thread(
        subprocess.run,
        [str(PROJECT_ROOT / ".venv/bin/alembic"), "upgrade", "head"],
        cwd=PROJECT_ROOT,
        env=migration_env,
        check=True,
        capture_output=True,
    )
    async with engine.begin() as connection:
        await connection.execute(text("SELECT 1"))

    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def test_session_factory(
    test_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def test_redis() -> AsyncGenerator[Redis, None]:
    redis = Redis.from_url(TEST_REDIS_URL, decode_responses=True)
    await redis.ping()
    await redis.flushdb()

    try:
        yield redis
    finally:
        await redis.flushdb()
        await redis.aclose()


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def isolate_test_state(
    test_session_factory: async_sessionmaker[AsyncSession],
    test_redis: Redis,
) -> AsyncGenerator[None, None]:
    async with test_session_factory() as session:
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(table.delete())
        await session.commit()

    await test_redis.flushdb()
    original_redis = session_service.redis
    session_service.redis = test_redis

    try:
        yield
    finally:
        session_service.redis = original_redis


@pytest_asyncio.fixture(loop_scope="session")
async def client(
    test_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with test_session_factory() as db:
        admin = User(
            email=f"admin-{uuid4().hex}@example.com",
            username=f"admin-{uuid4().hex}",
            role="admin",
            password_hash=hash_password("FixtureAdminPassword123!"),
        )
        db.add(admin)
        await db.commit()
        token = create_access_token(str(admin.id))
    transport = ASGITransport(app=app)

    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            client.headers["Authorization"] = f"Bearer {token}"
            client.test_session_factory = test_session_factory
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
