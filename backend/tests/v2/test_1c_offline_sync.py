"""
tests/v2/test_1c_offline_sync.py
Pruebas del servicio de sincronización offline con idempotencia (Fase 1C):
- Sincronización exitosa de lote con múltiples movimientos.
- Idempotencia estricta por uuid_local: reenvío no duplica ni altera stock.
- Aislamiento por movimiento: un movimiento rechazado (por capacidad) no bloquea al válido.
- Aislamiento multi-tenant: intento de usar recursos de otra organización es rechazado.
"""
import uuid
from decimal import Decimal
import pytest
from httpx import AsyncClient

from app.core.security import create_access_token
from app.models.usuario import Usuario
from app.models.v2 import (
    Organizacion, Sitio, Zona, Ubicacion,
    Item, Lote, TipoMovimiento, SaldoStock, UsuarioSitio
)
from sqlalchemy import select


@pytest.fixture
async def setup_sync_fixture(db):
    """Crea Organización A y B con usuarios, sitios, ubicaciones con límite de capacidad e ítems."""
    # Org A
    org_a = Organizacion(id=str(uuid.uuid4()), nombre="Logística Offline A", slug=f"sync-a-{uuid.uuid4().hex[:4]}")
    db.add(org_a)
    await db.flush()

    user_a = Usuario(
        id=str(uuid.uuid4()),
        nombre="Operario Offline A",
        email=f"offline_a_{uuid.uuid4().hex[:4]}@sync.cl",
        password_hash="fake",
        codigo_empleado=f"EMP-SNC-A-{uuid.uuid4().hex[:6]}",
        rol="operario",
        id_organizacion=org_a.id,
        activo=True,
    )
    db.add(user_a)
    await db.flush()

    sitio_a = Sitio(id=str(uuid.uuid4()), id_organizacion=org_a.id, codigo="SIT-A", nombre="Bodega Central A", tipo="bodega")
    db.add(sitio_a)
    await db.flush()
    db.add(UsuarioSitio(id_usuario=user_a.id, id_sitio=sitio_a.id))
    await db.flush()

    zona_a = Zona(id=str(uuid.uuid4()), id_organizacion=org_a.id, id_sitio=sitio_a.id, codigo="ZON-A", nombre="Zona A", tipo="sector")
    db.add(zona_a)
    await db.flush()

    # Ubicación con capacidad de 100 kg
    ubi_a1 = Ubicacion(
        id=str(uuid.uuid4()),
        id_organizacion=org_a.id,
        id_zona=zona_a.id,
        codigo="UBI-A1",
        capacidad_maxima=Decimal("100.0000"),
        unidad_capacidad="kg",
        ocupacion_actual=Decimal("0.0000"),
    )
    ubi_a2 = Ubicacion(
        id=str(uuid.uuid4()),
        id_organizacion=org_a.id,
        id_zona=zona_a.id,
        codigo="UBI-A2",
        capacidad_maxima=Decimal("50.0000"),
        unidad_capacidad="kg",
        ocupacion_actual=Decimal("0.0000"),
    )
    db.add_all([ubi_a1, ubi_a2])
    await db.flush()

    item_a = Item(
        id=str(uuid.uuid4()),
        id_organizacion=org_a.id,
        codigo="ITEM-A",
        nombre="Insumo Harina",
        categoria="materia_prima",
        unidad_medida="kg",
    )
    db.add(item_a)
    await db.flush()

    lote_a = Lote(id=str(uuid.uuid4()), id_organizacion=org_a.id, id_item=item_a.id, numero_lote="LOT-SYNC-01")
    db.add(lote_a)
    await db.flush()

    tipo_ingreso = TipoMovimiento(
        id=str(uuid.uuid4()),
        id_organizacion=org_a.id,
        codigo="ING_DIRECTO",
        nombre="Ingreso Directo",
        efecto_stock="entrada",
        requiere_destino=True,
        requiere_aprobacion=False,
    )
    db.add(tipo_ingreso)
    await db.flush()

    token_a = create_access_token({"sub": user_a.id, "org_id": org_a.id})

    # Org B
    org_b = Organizacion(id=str(uuid.uuid4()), nombre="Logística Offline B", slug=f"sync-b-{uuid.uuid4().hex[:4]}")
    db.add(org_b)
    await db.flush()

    sitio_b = Sitio(id=str(uuid.uuid4()), id_organizacion=org_b.id, codigo="SIT-B", nombre="Bodega Central B", tipo="bodega")
    db.add(sitio_b)
    await db.flush()

    zona_b = Zona(id=str(uuid.uuid4()), id_organizacion=org_b.id, id_sitio=sitio_b.id, codigo="ZON-B", nombre="Zona B", tipo="sector")
    db.add(zona_b)
    await db.flush()

    ubi_b = Ubicacion(
        id=str(uuid.uuid4()),
        id_organizacion=org_b.id,
        id_zona=zona_b.id,
        codigo="UBI-B1",
        capacidad_maxima=Decimal("500.0000"),
        unidad_capacidad="kg",
        ocupacion_actual=Decimal("0.0000"),
    )
    db.add(ubi_b)
    await db.flush()

    await db.commit()

    return {
        "org_a": org_a,
        "token_a": token_a,
        "user_a": user_a,
        "ubi_a1": ubi_a1,
        "ubi_a2": ubi_a2,
        "item_a": item_a,
        "lote_a": lote_a,
        "tipo_ingreso": tipo_ingreso,
        "org_b": org_b,
        "ubi_b": ubi_b,
    }


@pytest.mark.asyncio
async def test_offline_sync_batch_and_idempotency(client: AsyncClient, setup_sync_fixture, db):
    """Verifica sincronización de lote y que reintentos con mismo uuid_local sean idempotentes."""
    ctx = setup_sync_fixture
    headers = {"Authorization": f"Bearer {ctx['token_a']}"}

    uuid_1 = str(uuid.uuid4())
    uuid_2 = str(uuid.uuid4())

    batch_payload = {
        "movimientos": [
            {
                "uuid_local": uuid_1,
                "id_tipo_movimiento": ctx["tipo_ingreso"].id,
                "id_item": ctx["item_a"].id,
                "id_lote": ctx["lote_a"].id,
                "id_ubicacion_destino": ctx["ubi_a1"].id,
                "cantidad": 30.0,
                "unidad_medida": "kg",
                "observaciones": "Ingreso offline 1",
            },
            {
                "uuid_local": uuid_2,
                "id_tipo_movimiento": ctx["tipo_ingreso"].id,
                "id_item": ctx["item_a"].id,
                "id_lote": ctx["lote_a"].id,
                "id_ubicacion_destino": ctx["ubi_a1"].id,
                "cantidad": 20.0,
                "unidad_medida": "kg",
                "observaciones": "Ingreso offline 2",
            },
        ]
    }

    # 1. Primer envío: debe sincronizar ambos
    resp = await client.post("/api/v2/movimientos/sync", json=batch_payload, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 2
    assert data["sincronizados"] == 2
    assert data["rechazados"] == 0
    assert all(r["estado"] == "sincronizado" for r in data["resultados"])

    # Verificar saldo de stock consolidado (30 + 20 = 50 kg)
    stmt_saldo = select(SaldoStock).where(
        SaldoStock.id_ubicacion == ctx["ubi_a1"].id,
        SaldoStock.id_item == ctx["item_a"].id,
    )
    saldo = (await db.execute(stmt_saldo)).scalar_one_or_none()
    assert saldo is not None
    assert Decimal(str(saldo.cantidad)) == Decimal("50.0000")

    # 2. Reintento (exactamente el mismo lote reenviado por fallo de red)
    resp_reintento = await client.post("/api/v2/movimientos/sync", json=batch_payload, headers=headers)
    assert resp_reintento.status_code == 200
    data_reintento = resp_reintento.json()
    assert data_reintento["total"] == 2
    assert data_reintento["sincronizados"] == 2  # Idempotente cuenta como sincronizado previo
    assert all(r["estado"] == "duplicado" for r in data_reintento["resultados"])

    # Verificar que el stock NO se duplicó
    await db.refresh(saldo)
    assert Decimal(str(saldo.cantidad)) == Decimal("50.0000")


@pytest.mark.asyncio
async def test_offline_sync_partial_failure_isolated(client: AsyncClient, setup_sync_fixture, db):
    """Verifica que un movimiento inválido (supera capacidad) no impida que el válido se registre."""
    ctx = setup_sync_fixture
    headers = {"Authorization": f"Bearer {ctx['token_a']}"}

    uuid_valid = str(uuid.uuid4())
    uuid_invalid = str(uuid.uuid4())

    # ubi_a2 tiene capacidad 50 kg. Enviamos 25 kg (válido) y 80 kg (inválido por capacidad).
    batch_payload = {
        "movimientos": [
            {
                "uuid_local": uuid_valid,
                "id_tipo_movimiento": ctx["tipo_ingreso"].id,
                "id_item": ctx["item_a"].id,
                "id_lote": ctx["lote_a"].id,
                "id_ubicacion_destino": ctx["ubi_a2"].id,
                "cantidad": 25.0,
                "unidad_medida": "kg",
            },
            {
                "uuid_local": uuid_invalid,
                "id_tipo_movimiento": ctx["tipo_ingreso"].id,
                "id_item": ctx["item_a"].id,
                "id_lote": ctx["lote_a"].id,
                "id_ubicacion_destino": ctx["ubi_a2"].id,
                "cantidad": 80.0,  # Supera los 50 kg de ubi_a2
                "unidad_medida": "kg",
            },
        ]
    }

    resp = await client.post("/api/v2/movimientos/sync", json=batch_payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["sincronizados"] == 1
    assert data["rechazados"] == 1

    res_valid = next(r for r in data["resultados"] if r["uuid_local"] == uuid_valid)
    assert res_valid["estado"] == "sincronizado"
    assert res_valid["id_movimiento"] is not None

    res_invalid = next(r for r in data["resultados"] if r["uuid_local"] == uuid_invalid)
    assert res_invalid["estado"] == "rechazado"
    assert "capacidad" in res_invalid["motivo"].lower()

    # El saldo registrado en ubi_a2 debe ser solo los 25 kg
    stmt_saldo = select(SaldoStock).where(
        SaldoStock.id_ubicacion == ctx["ubi_a2"].id,
        SaldoStock.id_item == ctx["item_a"].id,
    )
    saldo = (await db.execute(stmt_saldo)).scalar_one_or_none()
    assert saldo is not None
    assert Decimal(str(saldo.cantidad)) == Decimal("25.0000")


@pytest.mark.asyncio
async def test_offline_sync_cross_tenant_rejected(client: AsyncClient, setup_sync_fixture):
    """Verifica que un usuario de Org A no pueda sincronizar un movimiento en una ubicación de Org B."""
    ctx = setup_sync_fixture
    headers = {"Authorization": f"Bearer {ctx['token_a']}"}

    uuid_cross = str(uuid.uuid4())
    batch_payload = {
        "movimientos": [
            {
                "uuid_local": uuid_cross,
                "id_tipo_movimiento": ctx["tipo_ingreso"].id,
                "id_item": ctx["item_a"].id,
                "id_ubicacion_destino": ctx["ubi_b"].id,  # Pertenece a Org B!
                "cantidad": 10.0,
                "unidad_medida": "kg",
            }
        ]
    }

    resp = await client.post("/api/v2/movimientos/sync", json=batch_payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["rechazados"] == 1

    res = data["resultados"][0]
    assert res["estado"] == "rechazado"
    assert "no encontrada" in res["motivo"].lower() or "pertenece" in res["motivo"].lower()
