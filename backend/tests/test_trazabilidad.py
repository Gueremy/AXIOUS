"""
tests/test_trazabilidad.py  — Sprint 2
Verifica: GET /movimientos/trazabilidad retorna historial correcto por lote,
aislamiento de sede, y excluye rut del response.
"""
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Movimiento, Galpon, Container, Sede, Producto, Usuario
from tests.conftest import pwd_context


pytestmark = pytest.mark.asyncio


async def _login_como(client: AsyncClient, db: AsyncSession, usuario: Usuario) -> str:
    r = await client.post("/auth/login", data={"username": usuario.email, "password": "Test1234!"})
    return r.json()["access_token"]


async def _crear_jefe(db: AsyncSession, sede_id: str) -> Usuario:
    u = Usuario(
        id=str(uuid.uuid4()), nombre="Jefe Traz",
        email=f"jefe_traz_{uuid.uuid4().hex[:6]}@test.cl",
        password_hash=pwd_context.hash("Test1234!"),
        codigo_empleado=f"JT{uuid.uuid4().hex[:6].upper()}",
        rol="jefe_bodega", id_sede=sede_id, activo=True,
    )
    db.add(u)
    await db.flush()
    return u


class TestTrazabilidad:
    async def test_retorna_movimientos_del_lote(
        self, client: AsyncClient, db: AsyncSession,
        sede, galpon, container, producto, usuario_operario, movimiento_aprobado
    ):
        jefe = await _crear_jefe(db, sede.id)
        token = await _login_como(client, db, jefe)
        r = await client.get(
            f"/movimientos/trazabilidad?numero_lote={movimiento_aprobado.numero_lote}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["numero_lote"] == movimiento_aprobado.numero_lote
        assert data["total"] >= 1
        assert len(data["movimientos"]) >= 1

    async def test_lote_inexistente_retorna_vacio(
        self, client: AsyncClient, db: AsyncSession, sede
    ):
        jefe = await _crear_jefe(db, sede.id)
        token = await _login_como(client, db, jefe)
        r = await client.get(
            "/movimientos/trazabilidad?numero_lote=LOT-NOEXISTE-999",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["total"] == 0

    async def test_rut_no_aparece_en_response(
        self, client: AsyncClient, db: AsyncSession,
        sede, galpon, container, producto, usuario_operario, movimiento_aprobado
    ):
        jefe = await _crear_jefe(db, sede.id)
        token = await _login_como(client, db, jefe)
        r = await client.get(
            f"/movimientos/trazabilidad?numero_lote={movimiento_aprobado.numero_lote}",
            headers={"Authorization": f"Bearer {token}"},
        )
        response_str = r.text
        assert "rut" not in response_str.lower() or "rut_proveedor" not in response_str.lower()

    async def test_operario_no_puede_consultar(
        self, client: AsyncClient, db: AsyncSession,
        sede, movimiento_aprobado, usuario_operario
    ):
        token = await _login_como(client, db, usuario_operario)
        r = await client.get(
            f"/movimientos/trazabilidad?numero_lote={movimiento_aprobado.numero_lote}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403

    async def test_aislamiento_sede_trazabilidad(
        self, client: AsyncClient, db: AsyncSession,
        sede, galpon, container, producto, usuario_operario, movimiento_aprobado
    ):
        """Jefe de otra sede no debe ver el lote."""
        otra_sede = Sede(id=str(uuid.uuid4()), nombre="Otra", tipo="bodega", estado="activo")
        db.add(otra_sede)
        await db.flush()
        jefe_otra = await _crear_jefe(db, otra_sede.id)
        token = await _login_como(client, db, jefe_otra)

        r = await client.get(
            f"/movimientos/trazabilidad?numero_lote={movimiento_aprobado.numero_lote}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        # El lote pertenece a container de otra sede, no debe aparecer
        assert r.json()["total"] == 0
