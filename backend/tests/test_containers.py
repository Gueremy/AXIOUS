"""
tests/test_containers.py  — Sprint 1
Verifica: paginacion con COUNT(*), aislamiento multi-sede, CRUD basico.
"""
import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import pwd_context
from app.models import Sede, Galpon, Container, Usuario


pytestmark = pytest.mark.asyncio


async def _token(client: AsyncClient, db: AsyncSession, rol: str = "operario", sede_id: str = None) -> str:
    u = Usuario(
        id=str(uuid.uuid4()),
        nombre=f"User {rol}",
        email=f"{rol}_{uuid.uuid4().hex[:6]}@test.cl",
        password_hash=pwd_context.hash("Test1234!"),
        codigo_empleado=f"C{uuid.uuid4().hex[:6].upper()}",
        rol=rol,
        id_sede=sede_id,
        activo=True,
    )
    db.add(u)
    await db.flush()
    r = await client.post("/auth/login", data={"username": u.email, "password": "Test1234!"})
    return r.json()["access_token"]


class TestListarContainers:
    async def test_retorna_estructura_paginada(self, client: AsyncClient, db: AsyncSession, sede, galpon, container):
        token = await _token(client, db, "operario", sede.id)
        r = await client.get("/containers/", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "size" in data
        assert "pages" in data

    async def test_total_es_entero_real(self, client: AsyncClient, db: AsyncSession, sede, galpon):
        # Crear 3 containers y verificar que total == 3
        for i in range(3):
            c = Container(
                id=str(uuid.uuid4()),
                id_galpon=galpon.id,
                codigo=f"T-{i}",
                posicion_fila=1,
                posicion_col=i+1,
                capacidad_max=Decimal("500.00"),
                unidad_medida="kg",
                ocupacion_actual=Decimal("0.00"),
                estado="disponible",
                tipo_producto_permitido="general",
            )
            db.add(c)
        await db.flush()
        token = await _token(client, db, "operario", sede.id)
        r = await client.get("/containers/", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data["total"], int)
        assert data["total"] >= 3

    async def test_paginacion_limit_funciona(self, client: AsyncClient, db: AsyncSession, sede, galpon):
        for i in range(5):
            c = Container(
                id=str(uuid.uuid4()),
                id_galpon=galpon.id,
                codigo=f"PAG-{i}",
                posicion_fila=2,
                posicion_col=i+1,
                capacidad_max=Decimal("500.00"),
                unidad_medida="kg",
                ocupacion_actual=Decimal("0.00"),
                estado="disponible",
                tipo_producto_permitido="general",
            )
            db.add(c)
        await db.flush()
        token = await _token(client, db, "operario", sede.id)
        r = await client.get("/containers/?limit=2", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert len(r.json()["items"]) <= 2

    async def test_aislamiento_multi_sede(self, client: AsyncClient, db: AsyncSession):
        # Crear 2 sedes con galpones y containers independientes
        sede_a = Sede(id=str(uuid.uuid4()), nombre="Sede A", tipo="planta", estado="activo")
        sede_b = Sede(id=str(uuid.uuid4()), nombre="Sede B", tipo="bodega", estado="activo")
        db.add(sede_a)
        db.add(sede_b)
        await db.flush()

        for sede in (sede_a, sede_b):
            g = Galpon(
                id=str(uuid.uuid4()), id_sede=sede.id,
                nombre="G", codigo=f"G{sede.nombre[-1]}", filas=3, columnas=3, estado="activo",
            )
            db.add(g)
            await db.flush()
            c = Container(
                id=str(uuid.uuid4()), id_galpon=g.id,
                codigo="C1", posicion_fila=1, posicion_col=1,
                capacidad_max=Decimal("100.00"), unidad_medida="kg",
                ocupacion_actual=Decimal("0.00"), estado="disponible",
                tipo_producto_permitido="general",
            )
            db.add(c)
        await db.flush()

        # Operario de Sede A solo ve containers de Sede A
        token_a = await _token(client, db, "operario", sede_a.id)
        r_a = await client.get("/containers/", headers={"Authorization": f"Bearer {token_a}"})
        ids_a = {item["id"] for item in r_a.json()["items"]}

        token_b = await _token(client, db, "operario", sede_b.id)
        r_b = await client.get("/containers/", headers={"Authorization": f"Bearer {token_b}"})
        ids_b = {item["id"] for item in r_b.json()["items"]}

        # No deben haber containers en comun
        assert ids_a.isdisjoint(ids_b), "Aislamiento fallido: containers de otra sede visibles"

    async def test_pages_calculadas_correctamente(self, client: AsyncClient, db: AsyncSession, sede, galpon):
        for i in range(10):
            c = Container(
                id=str(uuid.uuid4()), id_galpon=galpon.id,
                codigo=f"PC-{i}", posicion_fila=3, posicion_col=i+1,
                capacidad_max=Decimal("500.00"), unidad_medida="kg",
                ocupacion_actual=Decimal("0.00"), estado="disponible",
                tipo_producto_permitido="general",
            )
            db.add(c)
        await db.flush()
        token = await _token(client, db, "operario", sede.id)
        r = await client.get("/containers/?limit=3", headers={"Authorization": f"Bearer {token}"})
        data = r.json()
        expected_pages = -(-data["total"] // 3)  # ceil division
        assert data["pages"] == expected_pages
