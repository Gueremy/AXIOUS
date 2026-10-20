"""La exportación grande usa la misma instantánea mientras se escribe en paralelo."""
import json
import uuid
import zipfile

import pytest
from sqlalchemy import select

from app.api.v2 import exportaciones
from app.core.config import settings
from app.core.dependencies_v2 import TenantContext
from app.database import AsyncSessionLocal
from app.models.usuario import Usuario
from app.models.v2 import Item, Organizacion


@pytest.mark.asyncio(loop_scope="session")
async def test_zip_excludes_concurrent_insert_between_pages(monkeypatch):
    if "postgresql+asyncpg" not in settings.DATABASE_URL or "axious_v2_completion_test" not in settings.DATABASE_URL:
        pytest.skip("Requiere PostgreSQL axious_v2_completion_test")
    suffix = uuid.uuid4().hex[:12]
    item_id = lambda digit: f"{suffix[:8]}-0000-0000-0000-00000000000{digit}"
    org = Organizacion(id=str(uuid.uuid4()), nombre="Snapshot", slug=f"snap-{suffix}")
    user = Usuario(id=str(uuid.uuid4()), nombre="Exportador", email=f"snap-{suffix}@example.cl",
                   password_hash="unused", codigo_empleado=f"EX-{suffix}",
                   rol="super_admin", id_organizacion=org.id, activo=True)
    first = Item(id=item_id(1), id_organizacion=org.id,
                 codigo=f"A-{suffix}", nombre="Primero", categoria="general", unidad_medida="kg")
    last = Item(id=item_id(3), id_organizacion=org.id,
                codigo=f"C-{suffix}", nombre="Último", categoria="general", unidad_medida="kg")
    async with AsyncSessionLocal() as db:
        db.add(org)
        await db.flush()
        db.add_all([user, first, last])
        await db.commit()

    original = exportaciones.exportar_recurso

    async def insert_after_first_page(*args, **kwargs):
        response = await original(*args, **kwargs)
        if kwargs["page"] == 1:
            async with AsyncSessionLocal() as writer:
                writer.add(Item(id=item_id(2), id_organizacion=org.id,
                                codigo=f"B-{suffix}", nombre="Nuevo", categoria="general", unidad_medida="kg"))
                await writer.commit()
        return response

    monkeypatch.setattr(exportaciones, "exportar_recurso", insert_after_first_page)
    tenant = TenantContext(user, org, "super_admin", {"reporte:export"}, None)
    async with AsyncSessionLocal() as db:
        response = await exportaciones.exportar_recurso_completo(
            "items", "csv", size=1, tenant=tenant, db=db,
        )
    try:
        assert response.headers["X-Export-Total"] == "2"
        with zipfile.ZipFile(response.path) as archive:
            assert json.loads(archive.read("manifest.json"))["paginas"] == 2
            assert b"Primero" in archive.read("pagina-001.csv")
            assert b"\xc3\x9altimo" in archive.read("pagina-002.csv")
            assert b"Nuevo" not in archive.read("pagina-002.csv")
    finally:
        await response.background()
    async with AsyncSessionLocal() as db:
        items = (await db.execute(select(Item).where(Item.id_organizacion == org.id))).scalars().all()
        assert len(items) == 3
