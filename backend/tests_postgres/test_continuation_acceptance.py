"""Run the same export and recovery regressions against the migrated PostgreSQL schema."""
from contextlib import asynccontextmanager
import pytest
from httpx import ASGITransport, AsyncClient
from app.core.config import settings
from app.database import AsyncSessionLocal, get_db
from app.main import app
from tests.v2.test_1f_dashboard_and_export import (
    setup_dashboard_fixture,
    test_bi_complete_export_does_not_truncate_at_twenty_thousand as _large_export,
)
from tests.v2.test_1a_movements_concurrency import (
    setup_movimientos_fixture,
    test_compensation_lost_response_replays_with_original_link as _recover_compensation,
)


@asynccontextmanager
async def postgres_client():
    if "postgresql+asyncpg" not in settings.DATABASE_URL or "axious_v2_completion_test" not in settings.DATABASE_URL:
        pytest.skip("Requiere PostgreSQL aislado axious_v2_completion_test migrado")
    async with AsyncSessionLocal() as db:
        async def session():
            yield db
        app.dependency_overrides[get_db] = session
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                yield db, client
        finally:
            app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio(loop_scope="session")
async def test_twenty_thousand_movements_exported_from_postgres():
    async with postgres_client() as (db, client):
        # Reuse the synthetic dataset and assertions without the SQLite fixture binding.
        context = await setup_dashboard_fixture.__wrapped__(db)
        await _large_export(client, db, context)


@pytest.mark.asyncio(loop_scope="session")
async def test_lost_compensation_response_recovers_on_postgres():
    async with postgres_client() as (db, client):
        context = await setup_movimientos_fixture.__wrapped__(db)
        await _recover_compensation(client, context)
