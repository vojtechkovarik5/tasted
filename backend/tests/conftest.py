"""Shared fixtures for the integration test suite.

These are *integration* tests: they run against a real Postgres (the same
pgvector image the app uses), not a mock. Each test gets a clean, isolated
database transaction that is rolled back at the end, so tests never see each
other's writes and the dev database is left untouched.

The harness:
  * `_ensure_test_database` creates a dedicated `<db>_test` database once.
  * `engine`  — builds the schema (SQLAlchemy `create_all`, plus the pgvector
                extension the ORM models need).
  * `db_session` — one connection wrapped in an outer transaction; the ORM
                session commits become SAVEPOINT releases
                (`join_transaction_mode="create_savepoint"`), so the final
                `rollback()` reverts everything the test (and the endpoints it
                calls) committed.
  * `client` — an httpx AsyncClient bound to the FastAPI app, with the app's
                `get_session` dependency overridden to hand out `db_session`.

Point it at a running Postgres via the usual POSTGRES_* env (see .env.example);
`docker compose up db` is enough.
"""

from __future__ import annotations

from urllib.parse import quote_plus

import asyncpg
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import settings
from app.db import get_session
from app.models import Base
from app.routers import currencies, dishes, health, menus, preferences


def _build_test_app() -> FastAPI:
    """A minimal app with just the routers the tests exercise.

    We deliberately don't import `app.main`: it wires static-file mounts and
    the restrictions router, irrelevant to these tests. Mounting only what we
    test keeps the suite fast and focused.
    """
    test_app = FastAPI()
    test_app.include_router(health.router)
    test_app.include_router(currencies.router)
    test_app.include_router(preferences.router)
    test_app.include_router(menus.router)
    test_app.include_router(dishes.router)
    return test_app


app = _build_test_app()

# A separate database so tests never touch dev/prod data. Overridable if the
# real db is itself named "*_test" for some reason, but the default is fine.
TEST_DB_NAME = f"{settings.postgres_db}_test"


def _test_database_url() -> str:
    user = quote_plus(settings.postgres_user)
    password = quote_plus(settings.postgres_password)
    return (
        f"postgresql+asyncpg://{user}:{password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{TEST_DB_NAME}"
    )


async def _ensure_test_database() -> None:
    """Create the `<db>_test` database if it doesn't exist yet.

    Connects to the maintenance `postgres` database (CREATE DATABASE can't run
    inside the target db). The compose Postgres superuser can create it.
    """
    conn = await asyncpg.connect(
        user=settings.postgres_user,
        password=settings.postgres_password,
        host=settings.postgres_host,
        port=settings.postgres_port,
        database="postgres",
    )
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", TEST_DB_NAME
        )
        if not exists:
            # Identifier can't be parameterized; TEST_DB_NAME is derived from
            # our own config, not user input.
            await conn.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
    finally:
        await conn.close()


@pytest_asyncio.fixture
async def engine():
    """A test-database engine with a fresh schema matching the current models.

    Drop-then-create (rather than plain `create_all`, which skips existing
    tables) so a model change is always reflected — otherwise a table left
    over from an earlier run keeps its old columns. The SAVEPOINT rollback in
    `db_session` keeps rows out between tests; this handles schema drift.
    """
    await _ensure_test_database()
    eng = create_async_engine(_test_database_url())
    async with eng.begin() as conn:
        # ORM models declare pgvector columns; the type needs the extension.
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncSession:
    """An isolated session whose writes are rolled back after the test.

    The endpoints under test call `session.commit()`; with
    `join_transaction_mode="create_savepoint"` those commits release a
    savepoint instead of ending the outer transaction, which we roll back.
    """
    connection = await engine.connect()
    trans = await connection.begin()
    session = AsyncSession(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        await session.close()
        await trans.rollback()
        await connection.close()


@pytest_asyncio.fixture
def app_with_overrides() -> FastAPI:
    """The app instance the client serves — hand it to tests that need to
    register their own dependency overrides (e.g. injecting a fake storage)."""
    return app


@pytest_asyncio.fixture
async def client(db_session) -> AsyncClient:
    """FastAPI app client sharing the test's rolled-back session.

    Overriding `get_session` means every request in a test runs in the same
    transaction as the fixtures, so seeded rows are visible and nothing
    persists past the test.
    """

    async def _override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
