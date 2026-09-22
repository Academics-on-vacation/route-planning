"""Opt-in integration test: RUN_MIGRATION_TESTS=1, disposable PostgreSQL only."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_MIGRATION_TESTS") != "1",
    reason="requires an explicitly configured disposable PostgreSQL database",
)
BACKEND = Path(__file__).resolve().parents[1]


def alembic(*args: str) -> None:
    subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND, check=True)


async def query(statement: str):
    # Do not reuse app.config: other tests intentionally override its environment.
    url = URL.create(
        "postgresql+asyncpg",
        username=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        host=os.environ["DB_HOST"],
        port=int(os.environ["DB_PORT"]),
        database=os.environ["DB_NAME"],
    )
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            result = await connection.execute(text(statement))
            return result.scalar() if result.returns_rows else None
    finally:
        await engine.dispose()


def test_migration_lifecycle() -> None:
    alembic("upgrade", "head")
    alembic("check")
    asyncio.run(
        query(
            "INSERT INTO region (title, office_address, office_lat, office_lon) "
            "VALUES ('Migration test', 'Synthetic office', 55.75, 37.62)"
        )
    )
    alembic("upgrade", "head")
    assert asyncio.run(query("SELECT count(*) FROM region")) == 1
    alembic("downgrade", "base")
    assert (
        asyncio.run(
            query(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'public' "
                "AND table_name IN ('region', 'engineer', 'request', 'route_cache')"
            )
        )
        == 0
    )
    alembic("upgrade", "head")
    alembic("check")
