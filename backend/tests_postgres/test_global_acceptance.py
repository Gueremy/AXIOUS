"""Ejecuta el recorrido de aceptación completo sobre el esquema Alembic real."""
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.database import AsyncSessionLocal, get_db
from app.main import app
from tests.v2.test_global_acceptance_flow import test_global_acceptance_21_steps_journey as _run_global_journey


@pytest.mark.asyncio(loop_scope="session")
async def test_global_21_steps_on_postgres():
    if "postgresql+asyncpg" not in settings.DATABASE_URL or "axious_v2_completion_test" not in settings.DATABASE_URL:
        pytest.skip("Requiere DATABASE_URL de PostgreSQL axious_v2_completion_test")

    async with AsyncSessionLocal() as db:
        async def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                await _run_global_journey(client, db)
        finally:
            app.dependency_overrides.clear()
