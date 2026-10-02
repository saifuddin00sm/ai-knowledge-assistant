"""Test configuration.

Unit tests need nothing but the package. Integration tests need a real
PostgreSQL with pgvector; they are skipped unless `TEST_DATABASE_URL` is set.
The schema is created by running the real Alembic migration, so the migration
itself is covered too.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from urllib.parse import urlparse, urlunparse

import httpx
import pytest

# Must happen before anything imports app.core.config.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("LLM_PROVIDER", "fake")
os.environ.setdefault("EMBEDDING_PROVIDER", "hashing")
os.environ.setdefault("EMBEDDING_MODEL", "local-hashing-v1")
os.environ.setdefault("LOG_JSON", "true")
# INFO, not WARNING: the structured log calls carry domain fields and a key that
# shadows a LogRecord attribute raises at call time. Running the tests at INFO
# means every one of those calls is actually executed.
os.environ.setdefault("LOG_LEVEL", "INFO")
os.environ.setdefault("API_KEY", "")

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "").strip()
if TEST_DATABASE_URL:
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker  # noqa: E402

from app.db.session import dispose_engine, get_session_factory  # noqa: E402

TABLES = ("messages", "conversations", "chunks", "documents")


def _async_to_plain(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _maintenance_url(url: str) -> tuple[str, str]:
    """Split a database URL into (url pointing at `postgres`, target db name)."""
    parsed = urlparse(_async_to_plain(url))
    database = parsed.path.lstrip("/")
    return urlunparse(parsed._replace(path="/postgres")), database


async def _ensure_database(url: str) -> None:
    import asyncpg

    admin_url, database = _maintenance_url(url)
    connection = await asyncpg.connect(admin_url)
    try:
        exists = await connection.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", database)
        if not exists:
            await connection.execute(f'CREATE DATABASE "{database}"')
    finally:
        await connection.close()


@pytest.fixture(scope="session")
def database_url() -> str:
    if not TEST_DATABASE_URL:
        pytest.skip(
            "TEST_DATABASE_URL is not set; integration tests need PostgreSQL with pgvector. "
            "Try: docker compose up -d db && make test"
        )
    return TEST_DATABASE_URL


@pytest.fixture(scope="session")
def migrated_database(database_url: str) -> Iterator[str]:
    """Create the test database if needed and bring it to head."""
    from alembic import command
    from alembic.config import Config

    asyncio.run(_ensure_database(database_url))

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
    yield database_url


@pytest.fixture
async def session_factory(
    migrated_database: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """App-wide session factory, with every table emptied before each test.

    The engine is disposed around every test: pytest-asyncio gives each test a
    fresh event loop, and an asyncpg pool bound to a closed loop cannot be
    reused.
    """
    await dispose_engine()
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))
        await session.commit()
    yield factory
    await dispose_engine()


@pytest.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[httpx.AsyncClient]:
    """httpx client wired straight onto the ASGI app (no network, no server)."""
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver/api/v1", timeout=60.0
    ) as http_client:
        yield http_client
    app.dependency_overrides.clear()
