"""
tests/v2/test_3_layout_demo_and_integrations.py
Pruebas integrales de:
- Editor de Layout 2D/3D y creación masiva de ubicaciones (Fase 3).
- Generador de datos demo reproducibles (Fase 3B).
- Conectores externos, ingesta de eventos y webhooks firmados con HMAC (Fase 4).
"""
from decimal import Decimal
import uuid
import pytest
from httpx import AsyncClient

from app.core.events.event_bus import DomainEvent, EventBus
from app.core.security import create_access_token
from app.integraciones.webhooks import firmar_payload
from app.models.usuario import Usuario
from app.models.v2 import Organizacion, Sitio, Zona, Ubicacion


@pytest.fixture
async def setup_layout_integraciones_fixture(db):
    """Crea Organización para pruebas de Layout, Demo e Integraciones."""
    org = Organizacion(id=str(uuid.uuid4()), nombre="Logística Espacial", slug=f"lay-{uuid.uuid4().hex[:4]}")
    db.add(org)
    await db.flush()

    user = Usuario(
        id=str(uuid.uuid4()),
        nombre="Ingeniero Layout",
        email=f"lay_{uuid.uuid4().hex[:4]}@lay.cl",
        password_hash="fake",
        codigo_empleado=f"EMP-LAY-{uuid.uuid4().hex[:6]}",
        rol="super_admin",
        id_organizacion=org.id,
        activo=True,
    )
    db.add(user)
    await db.flush()

    sitio = Sitio(id=str(uuid.uuid4()), id_organizacion=org.id, codigo="SIT-LAY-01", nombre="Planta Maipú 3D", tipo="bodega")
    db.add(sitio)
    await db.flush()

    zona = Zona(
        id=str(uuid.uuid4()),
        id_organizacion=org.id,
        id_sitio=sitio.id,
        codigo="ZON-RACKS-A",
        nombre="Sector Racks Verticales",
        tipo="sector",
        layout={"x": 10, "y": 0, "z": 0, "width": 40, "height": 12, "depth": 20},
    )
    db.add(zona)
    await db.flush()

    ubi = Ubicacion(
        id=str(uuid.uuid4()),
        id_organizacion=org.id,
        id_zona=zona.id,
        codigo="BIN-A-01-01",
        capacidad_maxima=Decimal("1200.0000"),
        unidad_capacidad="kg",
        ocupacion_actual=Decimal("300.0000"),
        layout={"x": 10, "y": 0, "z": 1.5, "width": 1.2, "height": 1.5, "depth": 1.0},
    )
    db.add(ubi)
    await db.flush()

    token = create_access_token({"sub": user.id, "org_id": org.id})
    await db.commit()

    return {
        "org": org,
        "user": user,
        "token": token,
        "sitio": sitio,
        "zona": zona,
        "ubi": ubi,
    }


@pytest.mark.asyncio
async def test_layout_editor_endpoints_and_batch_creation(client: AsyncClient, setup_layout_integraciones_fixture):
    """Verifica consulta de árbol de layout 3D, actualización espacial y batch de ubicaciones."""
    ctx = setup_layout_integraciones_fixture
    headers = {"Authorization": f"Bearer {ctx['token']}"}

    # 1. Consultar árbol de layout del sitio
    resp_tree = await client.get(f"/api/v2/layout/sitios/{ctx['sitio'].id}", headers=headers)
    assert resp_tree.status_code == 200
    tree = resp_tree.json()
    assert tree["codigo"] == "SIT-LAY-01"
    assert len(tree["zonas"]) == 1
    zona_node = tree["zonas"][0]
    assert zona_node["layout"]["width"] == 40
    assert len(zona_node["ubicaciones"]) == 1
    assert zona_node["ubicaciones"][0]["layout"]["z"] == 1.5

    # 2. Modificar layout de zona
    resp_patch_zona = await client.patch(
        f"/api/v2/layout/zonas/{ctx['zona'].id}",
        headers=headers,
        json={"layout": {"x": 15, "y": 5, "z": 0, "width": 50}},
    )
    assert resp_patch_zona.status_code == 200
    assert resp_patch_zona.json()["layout"]["x"] == 15

    # 3. Modificar layout de ubicación
    resp_patch_ubi = await client.patch(
        f"/api/v2/layout/ubicaciones/{ctx['ubi'].id}",
        headers=headers,
        json={"layout": {"x": 12.5, "y": 1.0, "z": 3.0, "rotation": 90.0}},
    )
    assert resp_patch_ubi.status_code == 200
    assert resp_patch_ubi.json()["layout"]["rotation"] == 90.0

    # 4. Creación masiva (batch) de ubicaciones
    batch_payload = {
        "id_zona": ctx["zona"].id,
        "ubicaciones": [
            {
                "codigo": "BIN-A-01-02",
                "capacidad_maxima": 1000.0,
                "unidad_capacidad": "kg",
                "layout": {"x": 10, "y": 0, "z": 3.0},
            },
            {
                "codigo": "BIN-A-01-03",
                "capacidad_maxima": 1000.0,
                "unidad_capacidad": "kg",
                "layout": {"x": 10, "y": 0, "z": 4.5},
            },
        ],
    }
    resp_batch = await client.post("/api/v2/layout/ubicaciones/batch", headers=headers, json=batch_payload)
    assert resp_batch.status_code == 201
    assert resp_batch.json()["creadas"] == 2


@pytest.mark.asyncio
async def test_demo_generator_presets(client: AsyncClient, setup_layout_integraciones_fixture):
    """Verifica generación de presets demo (salmonera y general)."""
    ctx = setup_layout_integraciones_fixture
    headers = {"Authorization": f"Bearer {ctx['token']}"}

    # 1. Preset salmonera en organización actual
    resp_salm = await client.post("/api/v2/demo/seed?preset=salmonera&en_organizacion_actual=true", headers=headers)
    assert resp_salm.status_code == 201
    assert resp_salm.json()["preset"] == "salmonera"

    # 2. Preset general creando nueva organización
    resp_gen = await client.post("/api/v2/demo/seed?preset=general&en_organizacion_actual=false", headers=headers)
    assert resp_gen.status_code == 201
    assert resp_gen.json()["preset"] == "general"
    assert resp_gen.json()["id_organizacion"] != ctx["org"].id


@pytest.mark.asyncio
async def test_integraciones_eventos_y_conectores(client: AsyncClient, setup_layout_integraciones_fixture):
    """Verifica ingesta de eventos externos, registro de auditoría y prueba de conector."""
    ctx = setup_layout_integraciones_fixture
    headers = {"Authorization": f"Bearer {ctx['token']}"}

    # 1. Listar conectores disponibles
    resp_con = await client.get("/api/v2/integraciones/conectores", headers=headers)
    assert resp_con.status_code == 200
    conectores = resp_con.json()
    assert any(c["id"] == "mock_erp" for c in conectores)

    # 2. Probar conector
    resp_test = await client.post(
        "/api/v2/integraciones/conectores/mock_erp/probar",
        headers=headers,
        json={"configuracion": {"api_key": "secret_sap_token"}},
    )
    assert resp_test.status_code == 200
    assert resp_test.json()["conexion_exitosa"] is True

    # 3. Recibir evento externo (ej: báscula de pesaje o SAP)
    eventos_bus_capturados = []

    def capturar_evento_integracion(event: DomainEvent):
        eventos_bus_capturados.append(event)

    EventBus.subscribe("integracion.bascula.pesaje_completado", capturar_evento_integracion)

    payload_evento = {
        "id_evento_externo": "BASCULA-EV-9912",
        "tipo_evento": "pesaje_completado",
        "datos": {"peso_bruto_kg": 4520.5, "posicion": "BIN-A-01-01"},
    }
    resp_evt = await client.post(
        "/api/v2/integraciones/bascula/eventos",
        headers=headers,
        json=payload_evento,
    )
    assert resp_evt.status_code == 202
    assert resp_evt.json()["status"] == "accepted"

    # Verificar que el evento llegó al EventBus con aislamiento de organización
    assert len(eventos_bus_capturados) == 1
    assert eventos_bus_capturados[0].id_organizacion == ctx["org"].id
    assert eventos_bus_capturados[0].payload["datos"]["peso_bruto_kg"] == 4520.5

    EventBus.clear()


def test_webhooks_firma_hmac_sha256():
    """Verifica que la firma HMAC-SHA256 sea calculada de forma criptográfica estándar."""
    secreto = "clave_secreta_webhook_123"
    payload = b'{"evento":"movimiento.confirmado","cantidad":100}'
    firma = firmar_payload(payload, secreto)

    assert isinstance(firma, str)
    assert len(firma) == 64  # SHA-256 produce 64 caracteres hexadecimales

    # Verificar determinismo
    firma_dup = firmar_payload(payload, secreto)
    assert firma == firma_dup

    # Con secreto diferente la firma debe ser distinta
    firma_otra = firmar_payload(payload, "otro_secreto")
    assert firma != firma_otra
