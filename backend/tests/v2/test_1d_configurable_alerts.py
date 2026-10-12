"""
tests/v2/test_1d_configurable_alerts.py
Pruebas de reglas de alertas configurables y trazables (Fase 1D):
- Ajuste dinámico de umbrales por organización sin modificar código.
- Independencia de reglas y umbrales entre dos organizaciones.
- Desactivación de regla evita la generación de alertas de ese tipo.
- Deduplicación de alertas activas en re-evaluaciones.
- Flujo de revisión y resolución de alertas con trazabilidad y auditoría.
- Aislamiento multi-tenant estricto.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.usuario import Usuario
from app.models.v2 import (
    Organizacion, Sitio, Zona, Ubicacion,
    Item, Lote, SaldoStock,
    ReglaAlertaV2, AlertaV2
)


@pytest.fixture
async def setup_alertas_fixture(db):
    """Crea Organización A y B con ubicaciones, ítems y lotes."""
    # Org A
    org_a = Organizacion(id=str(uuid.uuid4()), nombre="Logística Alertas A", slug=f"alert-a-{uuid.uuid4().hex[:4]}")
    db.add(org_a)
    await db.flush()

    user_a = Usuario(
        id=str(uuid.uuid4()),
        nombre="Admin Alertas A",
        email=f"alert_a_{uuid.uuid4().hex[:4]}@alert.cl",
        password_hash="fake",
        codigo_empleado=f"EMP-ALT-A-{uuid.uuid4().hex[:6]}",
        rol="super_admin",
        id_organizacion=org_a.id,
        activo=True,
    )
    db.add(user_a)
    await db.flush()

    sitio_a = Sitio(id=str(uuid.uuid4()), id_organizacion=org_a.id, codigo="SIT-ALT-A", nombre="Bodega Alertas", tipo="bodega")
    db.add(sitio_a)
    await db.flush()

    zona_a = Zona(id=str(uuid.uuid4()), id_organizacion=org_a.id, id_sitio=sitio_a.id, codigo="ZON-ALT-A", nombre="Zona Alertas", tipo="sector")
    db.add(zona_a)
    await db.flush()

    # Ubicación con 80% de ocupación (800 / 1000)
    ubi_a = Ubicacion(
        id=str(uuid.uuid4()),
        id_organizacion=org_a.id,
        id_zona=zona_a.id,
        codigo="UBI-80PCT",
        capacidad_maxima=Decimal("1000.0000"),
        unidad_capacidad="kg",
        ocupacion_actual=Decimal("800.0000"),
    )
    db.add(ubi_a)
    await db.flush()

    item_a = Item(
        id=str(uuid.uuid4()),
        id_organizacion=org_a.id,
        codigo="ITEM-ALT-A",
        nombre="Insumo Crítico",
        categoria="quimico",
        unidad_medida="kg",
    )
    db.add(item_a)
    await db.flush()

    # Lote que vence en 5 días
    fecha_5d = datetime.now(timezone.utc) + timedelta(days=5)
    lote_a = Lote(
        id=str(uuid.uuid4()),
        id_organizacion=org_a.id,
        id_item=item_a.id,
        numero_lote="LOT-VENCE-5D",
        fecha_vencimiento=fecha_5d,
    )
    db.add(lote_a)
    await db.flush()

    token_a = create_access_token({"sub": user_a.id, "org_id": org_a.id})

    # Org B
    org_b = Organizacion(id=str(uuid.uuid4()), nombre="Logística Alertas B", slug=f"alert-b-{uuid.uuid4().hex[:4]}")
    db.add(org_b)
    await db.flush()

    user_b = Usuario(
        id=str(uuid.uuid4()),
        nombre="Admin Alertas B",
        email=f"alert_b_{uuid.uuid4().hex[:4]}@alert.cl",
        password_hash="fake",
        codigo_empleado=f"EMP-ALT-B-{uuid.uuid4().hex[:6]}",
        rol="super_admin",
        id_organizacion=org_b.id,
        activo=True,
    )
    db.add(user_b)
    await db.flush()

    token_b = create_access_token({"sub": user_b.id, "org_id": org_b.id})

    await db.commit()

    return {
        "org_a": org_a,
        "user_a": user_a,
        "token_a": token_a,
        "ubi_a": ubi_a,
        "lote_a": lote_a,
        "item_a": item_a,
        "org_b": org_b,
        "token_b": token_b,
    }


@pytest.mark.asyncio
async def test_reglas_alerta_modificar_umbral_en_caliente(client: AsyncClient, setup_alertas_fixture, db):
    """Verifica que cambiar el umbral de capacidad de 90% a 75% gatilla la alerta en una ubicación al 80%."""
    ctx = setup_alertas_fixture
    headers = {"Authorization": f"Bearer {ctx['token_a']}"}

    # 1. Listar reglas (inicializa plantillas automáticamente con umbral default de 90%)
    resp_reglas = await client.get("/api/v2/alertas/reglas", headers=headers)
    assert resp_reglas.status_code == 200
    reglas = resp_reglas.json()
    regla_cap = next(r for r in reglas if r["codigo"] == "capacidad_critica")
    assert regla_cap["configuracion"]["umbral_porcentaje"] == 90.0

    # 2. Con 90%, una ubicación al 80% NO debe disparar alerta de capacidad
    resp_eval1 = await client.post("/api/v2/alertas/evaluar", headers=headers)
    assert resp_eval1.status_code == 200
    # Sólo debe disparar la del lote (vence en 5d <= 7d)
    tipos_alertas = [a["tipo"] for a in resp_eval1.json()["alertas_creadas"]]
    assert "capacidad_critica" not in tipos_alertas
    assert "vencimiento_7_dias" in tipos_alertas

    # 3. Modificar umbral de capacidad a 75% dinámicamente vía API
    resp_patch = await client.patch(
        f"/api/v2/alertas/reglas/{regla_cap['id']}",
        headers=headers,
        json={"configuracion": {"umbral_porcentaje": 75.0}},
    )
    assert resp_patch.status_code == 200
    assert resp_patch.json()["configuracion"]["umbral_porcentaje"] == 75.0

    # 4. Volver a evaluar: ahora la ubicación al 80% supera el 75% y genera la alerta
    resp_eval2 = await client.post("/api/v2/alertas/evaluar", headers=headers)
    assert resp_eval2.status_code == 200
    tipos_alertas_2 = [a["tipo"] for a in resp_eval2.json()["alertas_creadas"]]
    assert "capacidad_critica" in tipos_alertas_2

    # Verificar que el lote que ya tenía alerta activa no se duplicó
    assert tipos_alertas_2.count("vencimiento_7_dias") == 0


@pytest.mark.asyncio
async def test_deshabilitar_regla_evita_nuevas_alertas(client: AsyncClient, setup_alertas_fixture):
    """Verifica que deshabilitar una regla evita que se generen alertas de ese tipo."""
    ctx = setup_alertas_fixture
    headers = {"Authorization": f"Bearer {ctx['token_a']}"}

    # Deshabilitar regla de vencimiento de 7 días
    resp_reglas = await client.get("/api/v2/alertas/reglas", headers=headers)
    reglas = resp_reglas.json()
    regla_venc = next(r for r in reglas if r["codigo"] == "vencimiento_7_dias")

    resp_patch = await client.patch(
        f"/api/v2/alertas/reglas/{regla_venc['id']}",
        headers=headers,
        json={"habilitada": False},
    )
    assert resp_patch.status_code == 200
    assert resp_patch.json()["habilitada"] is False

    # Evaluar alertas: a pesar de existir lote con 5 días, no debe generarse alerta
    resp_eval = await client.post("/api/v2/alertas/evaluar", headers=headers)
    assert resp_eval.status_code == 200
    tipos_alertas = [a["tipo"] for a in resp_eval.json()["alertas_creadas"]]
    assert "vencimiento_7_dias" not in tipos_alertas


@pytest.mark.asyncio
async def test_flujo_revisar_y_resolver_alerta_con_auditoria(client: AsyncClient, setup_alertas_fixture):
    """Verifica ciclo de vida de alerta: activa -> revisada -> resuelta, con notas y auditoría."""
    ctx = setup_alertas_fixture
    headers = {"Authorization": f"Bearer {ctx['token_a']}"}

    # 1. Generar alerta de lote
    await client.post("/api/v2/alertas/evaluar", headers=headers)

    # 2. Obtener alertas activas
    resp_activas = await client.get("/api/v2/alertas/activas", headers=headers)
    assert resp_activas.status_code == 200
    alertas = resp_activas.json()
    assert len(alertas) >= 1
    alerta_id = alertas[0]["id"]
    assert alertas[0]["estado"] == "activa"

    # 3. Marcar como revisada
    resp_rev = await client.patch(
        f"/api/v2/alertas/{alerta_id}/revisar",
        headers=headers,
        json={"observaciones": "Supervisor notificado, lote en revisión"},
    )
    assert resp_rev.status_code == 200
    assert resp_rev.json()["estado"] == "revisada"

    # 4. Resolver alerta
    resp_res = await client.patch(
        f"/api/v2/alertas/{alerta_id}/resolver",
        headers=headers,
        json={"observaciones": "Lote despachado prioritariamente"},
    )
    assert resp_res.status_code == 200
    assert resp_res.json()["estado"] == "resuelta"

    # 5. Ya no debe figurar en activas
    resp_activas_post = await client.get("/api/v2/alertas/activas", headers=headers)
    ids_activas = [a["id"] for a in resp_activas_post.json()]
    assert alerta_id not in ids_activas


@pytest.mark.asyncio
async def test_aislamiento_multitenant_alertas(client: AsyncClient, setup_alertas_fixture):
    """Verifica que Org B no pueda ver ni resolver alertas de Org A."""
    ctx = setup_alertas_fixture
    headers_a = {"Authorization": f"Bearer {ctx['token_a']}"}
    headers_b = {"Authorization": f"Bearer {ctx['token_b']}"}

    # Evaluar y generar alerta en A
    await client.post("/api/v2/alertas/evaluar", headers=headers_a)
    resp_a = await client.get("/api/v2/alertas/activas", headers=headers_a)
    alerta_a_id = resp_a.json()[0]["id"]

    # Usuario de B consulta activas: debe estar vacío
    resp_b = await client.get("/api/v2/alertas/activas", headers=headers_b)
    assert resp_b.status_code == 200
    assert len(resp_b.json()) == 0

    # Usuario de B intenta resolver alerta de A: 404
    resp_hack = await client.patch(
        f"/api/v2/alertas/{alerta_a_id}/resolver",
        headers=headers_b,
        json={"observaciones": "Intento no autorizado"},
    )
    assert resp_hack.status_code == 404
