"""
tests/v2/test_2_modular_architecture.py
Pruebas integrales de la arquitectura modular de SalmoTrack v2 (Fase 2):
- Bus de eventos interno desacoplado (Fase 2B).
- Catálogo de módulos y feature flags por organización (Fase 2C).
- Pack salmonero desacoplado: activo exige SAG/SERNAPESCA, inactivo opera limpio (Fase 2D).
- Estrategias de picking genéricas: FEFO, FIFO y LIFO (Fase 2E).
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid
import pytest
from httpx import AsyncClient

from app.core.events.event_bus import DomainEvent, EventBus
from app.core.modules.registry import ModuleRegistry
from app.core.security import create_access_token
from app.models.usuario import Usuario
from app.models.v2 import (
    Organizacion, Sitio, Zona, Ubicacion,
    Item, Lote, SaldoStock, TipoMovimiento, MovimientoV2
)


@pytest.mark.asyncio
async def test_modulos_apagados_bloquean_sus_rutas(client: AsyncClient, db, setup_modular_fixture):
    ctx = setup_modular_fixture
    org_id = ctx["org_a"].id
    headers = {"Authorization": f"Bearer {ctx['token_a']}"}

    for module_id in ("fefo", "importacion", "offline_sync"):
        await ModuleRegistry.set_module_status(db, org_id, module_id, False)

    picking = await client.get(
        f"/api/v2/picking/sugerir?id_item={ctx['item_harina'].id}&cantidad=1", headers=headers,
    )
    mappings = await client.get("/api/v2/importacion/mapeos", headers=headers)
    sync = await client.post("/api/v2/movimientos/sync", headers=headers, json={"movimientos": [{
        "uuid_local": str(uuid.uuid4()), "id_tipo_movimiento": ctx["tipo_ingreso"].id,
        "id_item": ctx["item_harina"].id, "id_ubicacion_destino": ctx["ubi_1"].id,
        "cantidad": 1, "unidad_medida": "kg",
    }]})
    assert [picking.status_code, mappings.status_code, sync.status_code] == [403, 403, 403]


@pytest.mark.asyncio
async def test_estrategia_picking_por_organizacion(client: AsyncClient, setup_modular_fixture):
    ctx = setup_modular_fixture
    headers = {"Authorization": f"Bearer {ctx['token_a']}"}
    changed = await client.patch("/api/v2/picking/estrategia", headers=headers, json={"estrategia": "lifo"})
    assert changed.status_code == 200
    response = await client.get(
        f"/api/v2/picking/sugerir?id_item={ctx['item_harina'].id}&cantidad=50", headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["estrategia"] == "lifo"
    assert response.json()["sugerencias"][0]["id_lote"] == ctx["lote_vence_10d"].id


@pytest.fixture
async def setup_modular_fixture(db):
    """Crea organizaciones con ítems y lotes con distintas fechas de vencimiento y creación."""
    # Org A
    org_a = Organizacion(id=str(uuid.uuid4()), nombre="Logística Modular A", slug=f"mod-a-{uuid.uuid4().hex[:4]}")
    db.add(org_a)
    await db.flush()

    user_a = Usuario(
        id=str(uuid.uuid4()),
        nombre="Admin Modular A",
        email=f"mod_a_{uuid.uuid4().hex[:4]}@mod.cl",
        password_hash="fake",
        codigo_empleado=f"EMP-MOD-A-{uuid.uuid4().hex[:6]}",
        rol="super_admin",
        id_organizacion=org_a.id,
        activo=True,
    )
    db.add(user_a)
    await db.flush()

    sitio_a = Sitio(id=str(uuid.uuid4()), id_organizacion=org_a.id, codigo="SIT-MOD-01", nombre="Bodega Modular", tipo="bodega")
    db.add(sitio_a)
    await db.flush()

    zona_a = Zona(id=str(uuid.uuid4()), id_organizacion=org_a.id, id_sitio=sitio_a.id, codigo="ZON-A", nombre="Sector Picking", tipo="sector")
    db.add(zona_a)
    await db.flush()

    ubi_1 = Ubicacion(
        id=str(uuid.uuid4()),
        id_organizacion=org_a.id,
        id_zona=zona_a.id,
        codigo="BIN-PICK-01",
        capacidad_maxima=Decimal("5000.0000"),
        unidad_capacidad="kg",
        ocupacion_actual=Decimal("100.0000"),
    )
    ubi_2 = Ubicacion(
        id=str(uuid.uuid4()),
        id_organizacion=org_a.id,
        id_zona=zona_a.id,
        codigo="BIN-PICK-02",
        capacidad_maxima=Decimal("5000.0000"),
        unidad_capacidad="kg",
        ocupacion_actual=Decimal("200.0000"),
    )
    db.add_all([ubi_1, ubi_2])
    await db.flush()

    item_harina = Item(
        id=str(uuid.uuid4()),
        id_organizacion=org_a.id,
        codigo="SKU-HARINA-01",
        nombre="Harina de Pescado Grado Prime",
        categoria="materia_prima",
        unidad_medida="kg",
    )
    db.add(item_harina)
    await db.flush()

    now = datetime.now(timezone.utc)
    # Lote 1: vence en 10 días, creado hace 5 días
    lote_vence_10d = Lote(
        id=str(uuid.uuid4()),
        id_organizacion=org_a.id,
        id_item=item_harina.id,
        numero_lote="LOT-V10D",
        fecha_vencimiento=now + timedelta(days=10),
        fecha_creacion=now - timedelta(days=5),
    )
    # Lote 2: vence en 30 días, creado hace 20 días (más antiguo en creación)
    lote_vence_30d = Lote(
        id=str(uuid.uuid4()),
        id_organizacion=org_a.id,
        id_item=item_harina.id,
        numero_lote="LOT-V30D",
        fecha_vencimiento=now + timedelta(days=30),
        fecha_creacion=now - timedelta(days=20),
    )
    db.add_all([lote_vence_10d, lote_vence_30d])
    await db.flush()

    # Saldos
    saldo_1 = SaldoStock(
        id_organizacion=org_a.id,
        id_ubicacion=ubi_1.id,
        id_item=item_harina.id,
        id_lote=lote_vence_10d.id,
        cantidad=Decimal("100.0000"),
        unidad_medida="kg",
    )
    saldo_2 = SaldoStock(
        id_organizacion=org_a.id,
        id_ubicacion=ubi_2.id,
        id_item=item_harina.id,
        id_lote=lote_vence_30d.id,
        cantidad=Decimal("200.0000"),
        unidad_medida="kg",
    )
    db.add_all([saldo_1, saldo_2])
    await db.flush()

    tipo_ingreso = TipoMovimiento(
        id=str(uuid.uuid4()),
        id_organizacion=org_a.id,
        codigo="ING_GENERICO",
        nombre="Ingreso Genérico",
        efecto_stock="entrada",
        requiere_destino=True,
        requiere_aprobacion=False,
    )
    db.add(tipo_ingreso)
    await db.flush()

    token_a = create_access_token({"sub": user_a.id, "org_id": org_a.id})

    await db.commit()

    return {
        "org_a": org_a,
        "token_a": token_a,
        "item_harina": item_harina,
        "lote_vence_10d": lote_vence_10d,
        "lote_vence_30d": lote_vence_30d,
        "tipo_ingreso": tipo_ingreso,
        "ubi_1": ubi_1,
    }


@pytest.mark.asyncio
async def test_event_bus_publish_subscribe_and_error_isolation():
    """Verifica que el event bus despache eventos y que un fallo en subscriber no aborte el flujo."""
    eventos_recibidos = []

    def subscriber_valido(event: DomainEvent):
        eventos_recibidos.append(event)

    def subscriber_con_error(event: DomainEvent):
        raise RuntimeError("Fallo simulado en plugin externo")

    EventBus.subscribe("test.evento", subscriber_valido)
    EventBus.subscribe("test.evento", subscriber_con_error)

    # Publicar
    test_event = DomainEvent(
        name="test.evento",
        id_organizacion="ORG-TEST",
        payload={"dato": 123},
    )
    # No debe levantar excepción a pesar de subscriber_con_error
    await EventBus.publish(test_event)

    assert len(eventos_recibidos) == 1
    assert eventos_recibidos[0].payload["dato"] == 123
    assert eventos_recibidos[0].id_organizacion == "ORG-TEST"

    EventBus.clear()


@pytest.mark.asyncio
async def test_module_registry_and_feature_flags_toggle(client: AsyncClient, setup_modular_fixture):
    """Verifica consulta de catálogo y activación/desactivación de módulos vía API."""
    ctx = setup_modular_fixture
    headers = {"Authorization": f"Bearer {ctx['token_a']}"}

    # 1. Consultar módulos
    resp = await client.get("/api/v2/modulos", headers=headers)
    assert resp.status_code == 200
    modulos = resp.json()
    pack = next(m for m in modulos if m["id"] == "pack_salmonero")
    # Pack salmonero inicia deshabilitado por defecto
    assert pack["habilitado"] is False

    # 2. Activar pack_salmonero
    resp_patch = await client.patch(
        "/api/v2/modulos/pack_salmonero",
        headers=headers,
        json={"habilitado": True},
    )
    assert resp_patch.status_code == 200
    assert resp_patch.json()["habilitado"] is True

    # 3. Consultar nuevamente
    resp_check = await client.get("/api/v2/modulos", headers=headers)
    pack_updated = next(m for m in resp_check.json() if m["id"] == "pack_salmonero")
    assert pack_updated["habilitado"] is True


@pytest.mark.asyncio
async def test_pack_salmonero_enforce_attributes_only_when_enabled(client: AsyncClient, setup_modular_fixture):
    """
    Verifica que:
    - Cuando pack_salmonero está OFF: registrar movimiento funciona sin atributos SAG/SERNAPESCA.
    - Cuando pack_salmonero está ON: registrar movimiento exige atributos normativos.
    - El reporte salmonero retorna 403 cuando está OFF y 200 cuando está ON.
    """
    ctx = setup_modular_fixture
    headers = {"Authorization": f"Bearer {ctx['token_a']}"}

    # Asegurar pack apagado
    await client.patch("/api/v2/modulos/pack_salmonero", headers=headers, json={"habilitado": False})

    # Reporte retorna 403 Forbidden cuando el pack está desactivado
    resp_rep_off = await client.get("/api/v2/modulos/salmonero/reporte", headers=headers)
    assert resp_rep_off.status_code == 403

    # Movimiento sin campos salmoneros: debe permitirse exitosamente (núcleo genérico limpio)
    payload_mov = {
        "id_tipo_movimiento": ctx["tipo_ingreso"].id,
        "id_item": ctx["item_harina"].id,
        "id_ubicacion_destino": ctx["ubi_1"].id,
        "cantidad": 10.0,
        "unidad_medida": "kg",
        "atributos": {},  # Sin campos SAG/SERNAPESCA
    }
    resp_mov_off = await client.post("/api/v2/movimientos/solicitudes", headers=headers, json=payload_mov)
    assert resp_mov_off.status_code == 201

    # Ahora activar el pack_salmonero
    await client.patch("/api/v2/modulos/pack_salmonero", headers=headers, json={"habilitado": True})

    # El reporte regulatorio ahora responde 200 OK
    resp_rep_on = await client.get("/api/v2/modulos/salmonero/reporte", headers=headers)
    assert resp_rep_on.status_code == 200
    assert resp_rep_on.json()["modulo"] == "pack_salmonero"

    # Intentar registrar movimiento sin atributos: debe ser RECHAZADO con 400
    resp_mov_fail = await client.post("/api/v2/movimientos/solicitudes", headers=headers, json=payload_mov)
    assert resp_mov_fail.status_code == 400
    assert "concesion_sernapesca" in resp_mov_fail.json()["detail"].lower()

    # Registrar movimiento con atributos normativos completos: debe ser aceptado
    payload_mov_valid = {
        **payload_mov,
        "atributos": {
            "codigo_concesion_sernapesca": "RES-SERNA-9812",
            "autorizacion_sag": "SAG-CERT-7711",
        },
    }
    resp_mov_ok = await client.post("/api/v2/movimientos/solicitudes", headers=headers, json=payload_mov_valid)
    assert resp_mov_ok.status_code == 201


@pytest.mark.asyncio
async def test_picking_strategies_fefo_fifo_lifo(client: AsyncClient, setup_modular_fixture):
    """
    Verifica las tres estrategias de picking:
    - FEFO: sugiere primero LOT-V10D (vence antes: 10d vs 30d).
    - FIFO: sugiere primero LOT-V30D (creado hace 20d, más antiguo que 5d).
    - LIFO: sugiere primero LOT-V10D (creado hace 5d, más reciente que 20d).
    """
    ctx = setup_modular_fixture
    headers = {"Authorization": f"Bearer {ctx['token_a']}"}
    item_id = ctx["item_harina"].id

    # 1. FEFO
    resp_fefo = await client.get(f"/api/v2/picking/sugerir?id_item={item_id}&cantidad=150&estrategia=fefo", headers=headers)
    assert resp_fefo.status_code == 200
    fefo_data = resp_fefo.json()
    assert fefo_data["sugerencias"][0]["numero_lote"] == "LOT-V10D"
    assert fefo_data["sugerencias"][1]["numero_lote"] == "LOT-V30D"

    # 2. FIFO
    resp_fifo = await client.get(f"/api/v2/picking/sugerir?id_item={item_id}&cantidad=150&estrategia=fifo", headers=headers)
    assert resp_fifo.status_code == 200
    fifo_data = resp_fifo.json()
    assert fifo_data["sugerencias"][0]["numero_lote"] == "LOT-V30D"  # Más antiguo en creación

    # 3. LIFO
    resp_lifo = await client.get(f"/api/v2/picking/sugerir?id_item={item_id}&cantidad=150&estrategia=lifo", headers=headers)
    assert resp_lifo.status_code == 200
    lifo_data = resp_lifo.json()
    assert lifo_data["sugerencias"][0]["numero_lote"] == "LOT-V10D"  # Más nuevo en creación
