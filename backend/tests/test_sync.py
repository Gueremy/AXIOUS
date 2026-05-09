"""
tests/test_sync.py  — Sprint 2
Verifica: POST /movimientos/sync inserta real en BD,
rechaza por capacidad, rechaza container inexistente.
"""
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Movimiento, Container
from tests.conftest import pwd_context


pytestmark = pytest.mark.asyncio


async def _login(client: AsyncClient, db: AsyncSession, sede_id: str) -> str:
    import uuid as _uuid
    from app.models import Usuario
    u = Usuario(
        id=str(_uuid.uuid4()),
        nombre="Sync User",
        email=f"sync_{_uuid.uuid4().hex[:6]}@test.cl",
        password_hash=pwd_context.hash("Test1234!"),
        codigo_empleado=f"SY{_uuid.uuid4().hex[:6].upper()}",
        rol="operario",
        id_sede=sede_id,
        activo=True,
    )
    db.add(u)
    await db.flush()
    r = await client.post("/auth/login", data={"username": u.email, "password": "Test1234!"})
    return r.json()["access_token"]


class TestSync:
    async def test_sync_vacio_retorna_resultados_vacio(
        self, client: AsyncClient, db: AsyncSession, sede
    ):
        token = await _login(client, db, sede.id)
        r = await client.post(
            "/movimientos/sync",
            json=[],
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201
        assert r.json()["resultados"] == []

    async def test_sync_container_inexistente_rechaza(
        self, client: AsyncClient, db: AsyncSession, sede, producto
    ):
        token = await _login(client, db, sede.id)
        payload = [{
            "uuid_local": "uuid-local-1",
            "id_container": str(uuid.uuid4()),  # no existe
            "id_producto": producto.id,
            "tipo": "entrada_proveedor",
            "cantidad": 100,
            "numero_lote": "LOT-OFF-001",
            "fecha_vencimiento": (datetime.utcnow() + timedelta(days=90)).isoformat(),
        }]
        r = await client.post(
            "/movimientos/sync",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201
        resultado = r.json()["resultados"][0]
        assert resultado["accion"] == "rechazar"
        assert "uuid_local" in resultado

    async def test_sync_sin_capacidad_rechaza(
        self, client: AsyncClient, db: AsyncSession, sede, galpon, producto
    ):
        # Container con capacidad maxima ya lleno
        c = Container(
            id=str(uuid.uuid4()), id_galpon=galpon.id,
            codigo="SYNC-LLENO", posicion_fila=4, posicion_col=1,
            capacidad_max=Decimal("100.00"),
            unidad_medida="kg",
            ocupacion_actual=Decimal("100.00"),  # lleno
            estado="disponible",
            tipo_producto_permitido="alimento",
        )
        db.add(c)
        await db.flush()

        token = await _login(client, db, sede.id)
        payload = [{
            "uuid_local": "uuid-lleno",
            "id_container": c.id,
            "id_producto": producto.id,
            "tipo": "entrada_proveedor",
            "cantidad": 50,
            "numero_lote": "LOT-OFF-002",
            "fecha_vencimiento": (datetime.utcnow() + timedelta(days=90)).isoformat(),
        }]
        r = await client.post(
            "/movimientos/sync",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201
        resultado = r.json()["resultados"][0]
        assert resultado["accion"] == "rechazar"
        assert "capacidad" in resultado["motivo"].lower() or "sin capacidad" in resultado["motivo"].lower()

    async def test_sync_ok_inserta_en_bd(
        self, client: AsyncClient, db: AsyncSession, sede, galpon, container, producto
    ):
        token = await _login(client, db, sede.id)
        uuid_local = f"uuid-ok-{uuid.uuid4().hex[:8]}"
        payload = [{
            "uuid_local": uuid_local,
            "id_container": container.id,
            "id_producto": producto.id,
            "tipo": "entrada_proveedor",
            "cantidad": 50,
            "numero_lote": "LOT-OFF-003",
            "fecha_vencimiento": (datetime.utcnow() + timedelta(days=90)).isoformat(),
            "nombre_proveedor": "BioMar",
            "num_guia_despacho": "GD-99",
            "registro_sanitario": "RS-99",
            "temperatura_almacen": -2.5,
        }]
        r = await client.post(
            "/movimientos/sync",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201
        resultado = r.json()["resultados"][0]
        assert resultado["accion"] == "aplicar"
        assert "id_movimiento" in resultado

        # Verificar que el movimiento existe en BD
        mov = (await db.execute(
            select(Movimiento).where(Movimiento.id == resultado["id_movimiento"])
        )).scalars().first()
        assert mov is not None
        assert mov.origen == "offline_sync"
        assert mov.estado == "pendiente"

    async def test_sync_multiples_mixtos(
        self, client: AsyncClient, db: AsyncSession, sede, galpon, container, producto
    ):
        token = await _login(client, db, sede.id)
        payload = [
            {   # OK
                "uuid_local": "mix-ok",
                "id_container": container.id,
                "id_producto": producto.id,
                "tipo": "entrada_proveedor",
                "cantidad": 10,
                "numero_lote": "LOT-MIX-1",
                "fecha_vencimiento": (datetime.utcnow() + timedelta(days=60)).isoformat(),
            },
            {   # Rechazar — container no existe
                "uuid_local": "mix-bad",
                "id_container": str(uuid.uuid4()),
                "id_producto": producto.id,
                "tipo": "entrada_proveedor",
                "cantidad": 10,
                "numero_lote": "LOT-MIX-2",
            },
        ]
        r = await client.post(
            "/movimientos/sync",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201
        resultados = r.json()["resultados"]
        assert len(resultados) == 2
        acciones = {res["uuid_local"]: res["accion"] for res in resultados}
        assert acciones["mix-ok"] == "aplicar"
        assert acciones["mix-bad"] == "rechazar"
