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
from app.models.v2.alerta import AlertaV2, ReglaAlertaV2
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

    alerts = await client.get("/api/v2/alertas/activas", headers=headers)
    assert alerts.status_code == 200
    offline_alerts = [a for a in alerts.json() if a["tipo"] == "sincronizacion_offline_rechazada"]
    assert len(offline_alerts) == 1
    assert offline_alerts[0]["id_ubicacion"] == ctx["ubi_a2"].id
    assert offline_alerts[0]["metadatos"]["uuid_local"] == uuid_invalid
    assert offline_alerts[0]["metadatos"]["id_usuario_solicitante"] == ctx["user_a"].id
    denied = await client.patch(
        f"/api/v2/alertas/{offline_alerts[0]['id']}/resolver", headers=headers,
    )
    assert denied.status_code == 403

    # Un reenvío puede repetir el rechazo, pero nunca duplicar la alerta.
    retry = await client.post("/api/v2/movimientos/sync", json=batch_payload, headers=headers)
    assert retry.status_code == 200
    assert retry.json()["rechazados"] == 1
    count = (await db.execute(select(AlertaV2).where(
        AlertaV2.id_organizacion == ctx["org_a"].id,
        AlertaV2.tipo == "sincronizacion_offline_rechazada",
    ))).scalars().all()
    assert len(count) == 1
    supervisor = Usuario(
        id=str(uuid.uuid4()), nombre="Supervisor Offline",
        email=f"supervisor_{uuid.uuid4().hex[:8]}@sync.cl", password_hash="fake",
        codigo_empleado=f"SUP-{uuid.uuid4().hex[:8]}", rol="jefe_bodega",
        id_organizacion=ctx["org_a"].id, activo=True,
    )
    db.add(supervisor)
    await db.flush()
    db.add(UsuarioSitio(id_usuario=supervisor.id, id_sitio=offline_alerts[0]["id_sitio"]))
    await db.commit()
    supervisor_token = create_access_token({"sub": supervisor.id, "org_id": ctx["org_a"].id})
    resolved = await client.patch(f"/api/v2/alertas/{offline_alerts[0]['id']}/resolver", headers={
        "Authorization": f"Bearer {supervisor_token}",
    })
    assert resolved.status_code == 200
    assert resolved.json()["estado"] == "resuelta"
    resolved_retry = await client.post("/api/v2/movimientos/sync", json=batch_payload, headers=headers)
    assert resolved_retry.status_code == 200
    assert len((await db.execute(select(AlertaV2).where(
        AlertaV2.id_organizacion == ctx["org_a"].id,
        AlertaV2.tipo == "sincronizacion_offline_rechazada",
    ))).scalars().all()) == 1

    rule = (await db.execute(select(ReglaAlertaV2).where(
        ReglaAlertaV2.id_organizacion == ctx["org_a"].id,
        ReglaAlertaV2.codigo == "sincronizacion_offline_rechazada",
    ))).scalar_one()
    rule.habilitada = False
    await db.commit()
    disabled = await client.post("/api/v2/movimientos/sync", headers=headers, json={"movimientos": [
        {**batch_payload["movimientos"][1], "uuid_local": str(uuid.uuid4())},
    ]})
    assert disabled.status_code == 200
    assert disabled.json()["rechazados"] == 1
    assert len((await db.execute(select(AlertaV2).where(
        AlertaV2.id_organizacion == ctx["org_a"].id,
        AlertaV2.tipo == "sincronizacion_offline_rechazada",
    ))).scalars().all()) == 1

    # El saldo registrado en ubi_a2 debe ser solo los 25 kg
    stmt_saldo = select(SaldoStock).where(
        SaldoStock.id_ubicacion == ctx["ubi_a2"].id,
        SaldoStock.id_item == ctx["item_a"].id,
    )
    saldo = (await db.execute(stmt_saldo)).scalar_one_or_none()
    assert saldo is not None
    assert Decimal(str(saldo.cantidad)) == Decimal("25.0000")


@pytest.mark.asyncio
async def test_offline_sync_cross_tenant_rejected(client: AsyncClient, setup_sync_fixture, db):
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
    alert = (await db.execute(select(AlertaV2).where(
        AlertaV2.id_organizacion == ctx["org_a"].id,
        AlertaV2.tipo == "sincronizacion_offline_rechazada",
    ))).scalar_one()
    assert alert.id_ubicacion is None
    assert alert.id_sitio is None


@pytest.mark.asyncio
async def test_transient_sync_is_retryable_and_hides_internal_details(client, setup_sync_fixture, monkeypatch):
    from app.services.v2.movimiento_service import MovimientoService
    async def unavailable(*args, **kwargs):
        raise RuntimeError("private database connection information")
    monkeypatch.setattr(MovimientoService, "crear_solicitud", unavailable)
    ctx=setup_sync_fixture
    response=await client.post("/api/v2/movimientos/sync",
        headers={"Authorization": f"Bearer {ctx['token_a']}"}, json={"movimientos":[{
            "uuid_local":str(uuid.uuid4()), "id_tipo_movimiento":ctx["tipo_ingreso"].id,
            "id_item":ctx["item_a"].id, "id_ubicacion_destino":ctx["ubi_a1"].id,
            "cantidad":2, "unidad_medida":"kg"}]})
    assert response.status_code == 200, response.text
    body=response.json()
    assert body["resultados"][0]["estado"] == "reintentar"
    assert body["reintentables"] == 1 and body["rechazados"] == 0
    assert "private database" not in response.text


@pytest.mark.asyncio
async def test_qr_v2_respects_tenant_scope(client, setup_sync_fixture):
    ctx=setup_sync_fixture
    headers={"Authorization":f"Bearer {ctx['token_a']}"}
    response=await client.get(f"/api/v2/ubicaciones/{ctx['ubi_a1'].id}/qr", headers=headers)
    assert response.status_code == 200, response.text
    assert "image/svg+xml" in response.headers["content-type"]
    assert "<svg" in response.text
    foreign=await client.get(f"/api/v2/ubicaciones/{ctx['ubi_b'].id}/qr", headers=headers)
    assert foreign.status_code == 404


@pytest.mark.asyncio
async def test_prepared_package_and_readable_ledger(client, setup_sync_fixture):
    ctx = setup_sync_fixture
    headers = {"Authorization": f"Bearer {ctx['token_a']}"}
    prepared = await client.get("/api/v2/sesion/offline", headers=headers)
    assert prepared.status_code == 200, prepared.text
    package = prepared.json()
    assert package["user_id"] == ctx["user_a"].id
    assert {row["id"] for row in package["locations"]} == {ctx["ubi_a1"].id, ctx["ubi_a2"].id}
    assert ctx["lote_a"].id in {row["id"] for row in package["lots"]}
    assert "password_hash" not in prepared.text
    create = await client.post("/api/v2/movimientos/solicitudes", headers=headers, json={
        "id_tipo_movimiento": ctx["tipo_ingreso"].id, "id_item": ctx["item_a"].id,
        "id_lote": ctx["lote_a"].id, "id_ubicacion_destino": ctx["ubi_a1"].id,
        "cantidad": 2, "unidad_medida": "kg"})
    assert create.status_code == 201, create.text
    ledger = await client.get("/api/v2/movimientos/?q=Insumo", headers=headers)
    assert ledger.status_code == 200, ledger.text
    row = ledger.json()["items"][0]
    assert row["item_nombre"] == ctx["item_a"].nombre
    assert row["numero_lote"] == ctx["lote_a"].numero_lote
    assert row["ubicacion_destino_codigo"] == ctx["ubi_a1"].codigo
    assert row["usuario_nombre"] == ctx["user_a"].nombre
    missing = await client.get("/api/v2/movimientos/?q=does-not-exist", headers=headers)
    assert missing.json()["total"] == 0


@pytest.mark.asyncio
async def test_new_lot_and_receipt_are_idempotent_and_keep_capture_time(client, setup_sync_fixture, db):
    ctx = setup_sync_fixture
    headers = {"Authorization": f"Bearer {ctx['token_a']}"}
    operation = {
        "uuid_local": str(uuid.uuid4()), "id_tipo_movimiento": ctx["tipo_ingreso"].id,
        "id_item": ctx["item_a"].id, "id_ubicacion_destino": ctx["ubi_a1"].id,
        "cantidad": 2, "unidad_medida": "kg", "fecha_hora_local": "2026-11-08T01:02:03Z",
        "lote_nuevo": {"numero_lote": "LOTE-NUEVO", "fecha_vencimiento": "2027-01-01T00:00:00Z",
            "proveedor": {"rut": "76.123.456-0", "razon_social": "Empresa de prueba"}},
    }
    first = await client.post("/api/v2/movimientos/sync", headers=headers, json={"movimientos": [operation]})
    assert first.json()["sincronizados"] == 1, first.text
    again = await client.post("/api/v2/movimientos/sync", headers=headers, json={"movimientos": [operation]})
    assert again.json()["resultados"][0]["estado"] == "duplicado", again.text
    lots = (await db.execute(select(Lote).where(Lote.id_item == ctx["item_a"].id, Lote.numero_lote == "LOTE-NUEVO"))).scalars().all()
    assert len(lots) == 1
    assert lots[0].atributos["proveedor"]["rut"] == "76123456-0"
    ledger = await client.get("/api/v2/movimientos/?q=LOTE-NUEVO", headers=headers)
    assert ledger.json()["total"] == 1
    assert ledger.json()["items"][0]["atributos"]["capturado_en_dispositivo"].startswith("2026-11-08T01:02:03")
    conflict = await client.post("/api/v2/movimientos/sync", headers=headers,
                                 json={"movimientos": [{**operation, "cantidad": 3}]})
    assert conflict.json()["resultados"][0]["estado"] == "rechazado", conflict.text


@pytest.mark.asyncio
async def test_invalid_supplier_rut_is_rejected_before_stock_changes(client, setup_sync_fixture):
    ctx = setup_sync_fixture
    response = await client.post("/api/v2/movimientos/solicitudes",
        headers={"Authorization": f"Bearer {ctx['token_a']}"}, json={
            "id_tipo_movimiento": ctx["tipo_ingreso"].id, "id_item": ctx["item_a"].id,
            "id_ubicacion_destino": ctx["ubi_a1"].id, "cantidad": 2, "unidad_medida": "kg",
            "lote_nuevo": {"numero_lote": "INVALIDO", "proveedor": {"rut": "76123456-1", "razon_social": "Prueba"}}})
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_request_status_lookup_keeps_id_filter_and_authorization(client, setup_sync_fixture):
    ctx = setup_sync_fixture
    headers = {"Authorization": f"Bearer {ctx['token_a']}"}
    created = await client.post("/api/v2/movimientos/solicitudes", headers=headers, json={
        "id_tipo_movimiento": ctx["tipo_ingreso"].id, "id_item": ctx["item_a"].id,
        "id_lote": ctx["lote_a"].id, "id_ubicacion_destino": ctx["ubi_a1"].id,
        "cantidad": 2, "unidad_medida": "kg"})
    assert created.status_code == 201, created.text
    request_id = created.json()["id"]
    found = await client.get(f"/api/v2/movimientos/solicitudes?ids={request_id}&ids={uuid.uuid4()}", headers=headers)
    assert found.status_code == 200, found.text
    assert [row["id"] for row in found.json()["items"]] == [request_id]
    missing = await client.get(f"/api/v2/movimientos/solicitudes?ids={uuid.uuid4()}", headers=headers)
    assert missing.status_code == 200 and missing.json()["total"] == 0
