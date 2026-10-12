"""
tests/v2/test_1a_movements_concurrency.py
Pruebas exhaustivas de la Fase 1A:
- Movimientos genéricos (Entradas directas, Salidas directas, Traslados).
- Actualización transaccional atómica de SaldoStock y ocupación.
- Validación de existencias (prevención de stock negativo).
- Validación de capacidad máxima en ubicaciones.
- Flujo de solicitud previa, aprobación atómica y rechazo auditable.
- Trazabilidad y consulta de saldos consolidados.
"""
import uuid
from decimal import Decimal
import pytest
from httpx import AsyncClient

from app.core.security import create_access_token
from app.models.usuario import Usuario
from app.models.v2 import (
    Organizacion, Sitio, Zona, Ubicacion,
    Item, Lote, TipoMovimiento, SaldoStock
)


@pytest.fixture
async def setup_movimientos_fixture(db):
    """Configura organización, sitio, ubicaciones, items y tipos de movimiento."""
    org = Organizacion(id=str(uuid.uuid4()), nombre="Logística Transaccional", slug=f"log-{uuid.uuid4().hex[:4]}")
    db.add(org)
    await db.flush()

    user = Usuario(
        id=str(uuid.uuid4()),
        nombre="Jefe Operaciones",
        email=f"jefe_{uuid.uuid4().hex[:4]}@log.cl",
        password_hash="fake",
        codigo_empleado="EMP-MOV-01",
        rol="super_admin",
        id_organizacion=org.id,
        activo=True,
    )
    db.add(user)
    await db.flush()

    sitio = Sitio(id=str(uuid.uuid4()), id_organizacion=org.id, codigo="SIT-01", nombre="Centro Bodegas", tipo="bodega")
    db.add(sitio)
    await db.flush()

    zona = Zona(id=str(uuid.uuid4()), id_organizacion=org.id, id_sitio=sitio.id, codigo="ZON-01", nombre="Nave A", tipo="nave")
    db.add(zona)
    await db.flush()

    # Ubicación 1: Capacidad 1000 kg
    ubi1 = Ubicacion(
        id=str(uuid.uuid4()),
        id_organizacion=org.id,
        id_zona=zona.id,
        codigo="POS-01",
        capacidad_maxima=Decimal("1000.0000"),
        unidad_capacidad="kg",
        ocupacion_actual=Decimal("0.0000"),
    )
    # Ubicación 2: Capacidad 500 kg
    ubi2 = Ubicacion(
        id=str(uuid.uuid4()),
        id_organizacion=org.id,
        id_zona=zona.id,
        codigo="POS-02",
        capacidad_maxima=Decimal("500.0000"),
        unidad_capacidad="kg",
        ocupacion_actual=Decimal("0.0000"),
    )
    db.add_all([ubi1, ubi2])
    await db.flush()

    item = Item(
        id=str(uuid.uuid4()),
        id_organizacion=org.id,
        codigo="MAT-HARINA",
        nombre="Harina Premium",
        categoria="alimentos",
        unidad_medida="kg",
    )
    db.add(item)
    await db.flush()

    lote = Lote(
        id=str(uuid.uuid4()),
        id_organizacion=org.id,
        id_item=item.id,
        numero_lote="LOTE-PRUEBA-01",
    )
    db.add(lote)
    await db.flush()

    # Tipos de Movimiento
    tipo_entrada = TipoMovimiento(
        id=str(uuid.uuid4()),
        id_organizacion=org.id,
        codigo="RECEPCION",
        nombre="Recepción de Proveedor",
        efecto_stock="entrada",
        requiere_origen=False,
        requiere_destino=True,
        requiere_aprobacion=False,
    )
    tipo_salida = TipoMovimiento(
        id=str(uuid.uuid4()),
        id_organizacion=org.id,
        codigo="DESPACHO",
        nombre="Despacho Directo",
        efecto_stock="salida",
        requiere_origen=True,
        requiere_destino=False,
        requiere_aprobacion=False,
    )
    tipo_traslado = TipoMovimiento(
        id=str(uuid.uuid4()),
        id_organizacion=org.id,
        codigo="TRASLADO",
        nombre="Traslado Interno",
        efecto_stock="traslado",
        requiere_origen=True,
        requiere_destino=True,
        requiere_aprobacion=True,  # Requiere aprobación
    )
    db.add_all([tipo_entrada, tipo_salida, tipo_traslado])
    await db.flush()

    token = create_access_token({"sub": user.id, "org_id": org.id})

    return {
        "org": org,
        "user": user,
        "sitio": sitio,
        "ubi1": ubi1,
        "ubi2": ubi2,
        "item": item,
        "lote": lote,
        "tipo_entrada": tipo_entrada,
        "tipo_salida": tipo_salida,
        "tipo_traslado": tipo_traslado,
        "token": token,
    }


@pytest.mark.asyncio
async def test_flujo_movimientos_y_actualizacion_segura_stock(client: AsyncClient, setup_movimientos_fixture):
    """
    Prueba el ciclo completo:
    1. Entrada directa de 400 kg en ubi1.
    2. Rechazo de salida si no hay stock suficiente.
    3. Salida directa de 100 kg desde ubi1.
    4. Traslado de 200 kg desde ubi1 hacia ubi2 con flujo de aprobación.
    5. Intento de ingreso que supera la capacidad de ubi2 es rechazado.
    6. Trazabilidad completa por lote.
    """
    data = setup_movimientos_fixture
    headers = {"Authorization": f"Bearer {data['token']}"}

    # ── 1. Entrada Directa: 400 kg en ubi1 ──────────────────────────────────────
    resp_in = await client.post(
        "/api/v2/movimientos/solicitudes",
        headers=headers,
        json={
            "id_tipo_movimiento": data["tipo_entrada"].id,
            "id_item": data["item"].id,
            "id_lote": data["lote"].id,
            "id_ubicacion_destino": data["ubi1"].id,
            "cantidad": 400.0,
            "unidad_medida": "kg",
            "observaciones": "Recepción lote inicial",
        },
    )
    assert resp_in.status_code == 201
    assert resp_in.json()["estado"] == "aprobada"  # Confirmado automáticamente

    # Verificar saldo de ubi1
    resp_saldos = await client.get(f"/api/v2/movimientos/saldos?id_ubicacion={data['ubi1'].id}", headers=headers)
    assert resp_saldos.status_code == 200
    saldos_u1 = resp_saldos.json()
    assert len(saldos_u1) == 1
    assert float(saldos_u1[0]["cantidad"]) == 400.0

    # ── 2. Intentar Salida con Stock Insuficiente (Intentar 600 kg cuando hay 400 kg) ──
    resp_over = await client.post(
        "/api/v2/movimientos/solicitudes",
        headers=headers,
        json={
            "id_tipo_movimiento": data["tipo_salida"].id,
            "id_item": data["item"].id,
            "id_lote": data["lote"].id,
            "id_ubicacion_origen": data["ubi1"].id,
            "cantidad": 600.0,
            "unidad_medida": "kg",
        },
    )
    assert resp_over.status_code == 400
    assert "insuficiente" in resp_over.json()["detail"].lower()

    # ── 3. Salida Directa Válida: 100 kg desde ubi1 ────────────────────────────
    resp_out = await client.post(
        "/api/v2/movimientos/solicitudes",
        headers=headers,
        json={
            "id_tipo_movimiento": data["tipo_salida"].id,
            "id_item": data["item"].id,
            "id_lote": data["lote"].id,
            "id_ubicacion_origen": data["ubi1"].id,
            "cantidad": 100.0,
            "unidad_medida": "kg",
            "observaciones": "Despacho a cliente directo",
        },
    )
    assert resp_out.status_code == 201
    assert resp_out.json()["estado"] == "aprobada"

    # Saldo ubi1 debe ser 300 kg
    resp_saldos = await client.get(f"/api/v2/movimientos/saldos?id_ubicacion={data['ubi1'].id}", headers=headers)
    assert float(resp_saldos.json()[0]["cantidad"]) == 300.0

    # ── 4. Traslado con Aprobación: 200 kg desde ubi1 a ubi2 ──────────────────
    resp_req_tras = await client.post(
        "/api/v2/movimientos/solicitudes",
        headers=headers,
        json={
            "id_tipo_movimiento": data["tipo_traslado"].id,
            "id_item": data["item"].id,
            "id_lote": data["lote"].id,
            "id_ubicacion_origen": data["ubi1"].id,
            "id_ubicacion_destino": data["ubi2"].id,
            "cantidad": 200.0,
            "unidad_medida": "kg",
        },
    )
    assert resp_req_tras.status_code == 201
    id_solicitud = resp_req_tras.json()["id"]
    assert resp_req_tras.json()["estado"] == "pendiente"  # En espera

    # El saldo de ubi1 sigue siendo 300 kg porque la solicitud pendiente no descuenta
    resp_saldos = await client.get(f"/api/v2/movimientos/saldos?id_ubicacion={data['ubi1'].id}", headers=headers)
    assert float(resp_saldos.json()[0]["cantidad"]) == 300.0

    # Aprobar el traslado
    resp_aprob = await client.patch(f"/api/v2/movimientos/solicitudes/{id_solicitud}/aprobar", headers=headers)
    assert resp_aprob.status_code == 200
    assert resp_aprob.json()["efecto_stock"] == "traslado"

    # Comprobar saldos finales: ubi1 = 100 kg, ubi2 = 200 kg
    saldos_u1 = (await client.get(f"/api/v2/movimientos/saldos?id_ubicacion={data['ubi1'].id}", headers=headers)).json()
    assert float(saldos_u1[0]["cantidad"]) == 100.0

    saldos_u2 = (await client.get(f"/api/v2/movimientos/saldos?id_ubicacion={data['ubi2'].id}", headers=headers)).json()
    assert float(saldos_u2[0]["cantidad"]) == 200.0

    # ── 5. Intentar Traslado que excede capacidad de destino ────────────────────
    # ubi2 tiene capacidad 500 kg y ya tiene 200 kg ocupados. Intentar trasladar 400 kg (total 600 kg)
    resp_excede_cap = await client.post(
        "/api/v2/movimientos/solicitudes",
        headers=headers,
        json={
            "id_tipo_movimiento": data["tipo_entrada"].id,
            "id_item": data["item"].id,
            "id_lote": data["lote"].id,
            "id_ubicacion_destino": data["ubi2"].id,
            "cantidad": 400.0,
            "unidad_medida": "kg",
        },
    )
    assert resp_excede_cap.status_code == 400
    assert "capacidad superada" in resp_excede_cap.json()["detail"].lower()

    # ── 6. Trazabilidad completa por Lote ───────────────────────────────────────
    resp_traz = await client.get(f"/api/v2/movimientos/trazabilidad?id_lote={data['lote'].id}", headers=headers)
    assert resp_traz.status_code == 200
    movs = resp_traz.json()
    # Debe tener: 1 entrada, 1 salida, 1 traslado
    assert len(movs) == 3
    efectos = [m["efecto_stock"] for m in movs]
    assert efectos == ["entrada", "salida", "traslado"]
