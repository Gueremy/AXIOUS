"""
tests/v2/test_1b_rule_engine.py
Pruebas del motor de reglas configurables de almacenamiento (Fase 1B):
- Prohibición de mezcla de lotes en una misma ubicación.
- Restricción de categorías de ítems permitidos.
- Dinamismo: modificar o desactivar una regla cambia el comportamiento en caliente.
- Errores estructurados y auditables.
"""
import uuid
from decimal import Decimal
import pytest
from httpx import AsyncClient

from app.core.security import create_access_token
from app.models.usuario import Usuario
from app.models.v2 import (
    Organizacion, Sitio, Zona, Ubicacion,
    Item, Lote, TipoMovimiento
)


@pytest.fixture
async def setup_rules_fixture(db):
    """Crea organización, ubicación y dos ítems con lotes distintos."""
    org = Organizacion(id=str(uuid.uuid4()), nombre="Logística Inteligente", slug=f"rules-{uuid.uuid4().hex[:4]}")
    db.add(org)
    await db.flush()

    user = Usuario(
        id=str(uuid.uuid4()),
        nombre="Admin Reglas",
        email=f"rules_{uuid.uuid4().hex[:4]}@rules.cl",
        password_hash="fake",
        codigo_empleado=f"EMP-RUL-{uuid.uuid4().hex[:6]}",
        rol="super_admin",
        id_organizacion=org.id,
        activo=True,
    )
    db.add(user)
    await db.flush()

    sitio = Sitio(id=str(uuid.uuid4()), id_organizacion=org.id, codigo="SIT-RUL-01", nombre="Bodega Norte", tipo="bodega")
    db.add(sitio)
    await db.flush()

    zona = Zona(id=str(uuid.uuid4()), id_organizacion=org.id, id_sitio=sitio.id, codigo="ZON-A", nombre="Sector Químicos", tipo="sector")
    db.add(zona)
    await db.flush()

    # Ubicación que no permite mezcla de lotes
    ubi = Ubicacion(
        id=str(uuid.uuid4()),
        id_organizacion=org.id,
        id_zona=zona.id,
        codigo="POS-PUR-01",
        capacidad_maxima=Decimal("2000.0000"),
        unidad_capacidad="kg",
        ocupacion_actual=Decimal("0.0000"),
        permite_mezcla_lotes=False,  # NO permite mezcla
    )
    db.add(ubi)
    await db.flush()

    item_mp = Item(
        id=str(uuid.uuid4()),
        id_organizacion=org.id,
        codigo="MAT-PRIM-01",
        nombre="Materia Prima Concentrada",
        categoria="materia_prima",
        unidad_medida="kg",
    )
    item_repuesto = Item(
        id=str(uuid.uuid4()),
        id_organizacion=org.id,
        codigo="REP-MOTOR-01",
        nombre="Repuesto de Motor",
        categoria="repuesto",
        unidad_medida="kg",
    )
    db.add_all([item_mp, item_repuesto])
    await db.flush()

    lote_a = Lote(id=str(uuid.uuid4()), id_organizacion=org.id, id_item=item_mp.id, numero_lote="LOTE-A")
    lote_b = Lote(id=str(uuid.uuid4()), id_organizacion=org.id, id_item=item_mp.id, numero_lote="LOTE-B")
    db.add_all([lote_a, lote_b])
    await db.flush()

    tipo_in = TipoMovimiento(
        id=str(uuid.uuid4()),
        id_organizacion=org.id,
        codigo="INGRESO_DIRECTO",
        nombre="Ingreso Directo",
        efecto_stock="entrada",
        requiere_destino=True,
        requiere_aprobacion=False,
    )
    db.add(tipo_in)
    await db.flush()

    token = create_access_token({"sub": user.id, "org_id": org.id})

    return {
        "org": org,
        "user": user,
        "ubi": ubi,
        "item_mp": item_mp,
        "item_repuesto": item_repuesto,
        "lote_a": lote_a,
        "lote_b": lote_b,
        "tipo_in": tipo_in,
        "token": token,
    }


@pytest.mark.asyncio
async def test_regla_mezcla_lotes_bloquea_segundo_lote(client: AsyncClient, setup_rules_fixture):
    """Verifica que si una ubicación prohíbe mezcla de lotes, se rechaza el ingreso de un segundo lote."""
    data = setup_rules_fixture
    headers = {"Authorization": f"Bearer {data['token']}"}

    # 1. Ingresar lote A (400 kg) en la ubicación
    resp1 = await client.post(
        "/api/v2/movimientos/solicitudes",
        headers=headers,
        json={
            "id_tipo_movimiento": data["tipo_in"].id,
            "id_item": data["item_mp"].id,
            "id_lote": data["lote_a"].id,
            "id_ubicacion_destino": data["ubi"].id,
            "cantidad": 400.0,
            "unidad_medida": "kg",
        },
    )
    assert resp1.status_code == 201

    # 2. Intentar ingresar lote B en la misma ubicación (debe fallar por regla de mezcla)
    resp2 = await client.post(
        "/api/v2/movimientos/solicitudes",
        headers=headers,
        json={
            "id_tipo_movimiento": data["tipo_in"].id,
            "id_item": data["item_mp"].id,
            "id_lote": data["lote_b"].id,
            "id_ubicacion_destino": data["ubi"].id,
            "cantidad": 200.0,
            "unidad_medida": "kg",
        },
    )
    assert resp2.status_code == 400
    assert "prohíbe la mezcla" in resp2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_regla_categorias_permitidas_y_modificacion_en_caliente(client: AsyncClient, setup_rules_fixture):
    """
    Verifica que:
    1. Una regla de categorías permitidas bloquea ítems de categorías no autorizadas.
    2. Al desactivar la regla vía API, el comportamiento cambia inmediatamente sin reiniciar Python.
    """
    data = setup_rules_fixture
    headers = {"Authorization": f"Bearer {data['token']}"}

    # 1. Crear regla: solo permite categoría 'materia_prima' en la ubicación
    resp_regla = await client.post(
        "/api/v2/reglas/",
        headers=headers,
        json={
            "codigo": "SOLO_MATERIA_PRIMA",
            "nombre": "Exclusivo Materias Primas",
            "tipo_regla": "categorias_permitidas",
            "id_ubicacion": data["ubi"].id,
            "configuracion": {"categorias": ["materia_prima"]},
        },
    )
    assert resp_regla.status_code == 201
    regla_id = resp_regla.json()["id"]

    # 2. Intentar ingresar item de categoría 'repuesto' -> Rechazado por regla
    resp_bad = await client.post(
        "/api/v2/movimientos/solicitudes",
        headers=headers,
        json={
            "id_tipo_movimiento": data["tipo_in"].id,
            "id_item": data["item_repuesto"].id,
            "id_ubicacion_destino": data["ubi"].id,
            "cantidad": 10.0,
            "unidad_medida": "kg",
        },
    )
    assert resp_bad.status_code == 400
    assert "no está permitida" in resp_bad.json()["detail"].lower()

    # 3. Desactivar la regla en caliente vía API
    resp_patch = await client.patch(
        f"/api/v2/reglas/{regla_id}",
        headers=headers,
        json={"activo": False},
    )
    assert resp_patch.status_code == 200
    assert resp_patch.json()["activo"] is False

    # 4. Reintentar el ingreso del repuesto -> Ahora es aceptado!
    resp_ok = await client.post(
        "/api/v2/movimientos/solicitudes",
        headers=headers,
        json={
            "id_tipo_movimiento": data["tipo_in"].id,
            "id_item": data["item_repuesto"].id,
            "id_ubicacion_destino": data["ubi"].id,
            "cantidad": 10.0,
            "unidad_medida": "kg",
        },
    )
    assert resp_ok.status_code == 201
    assert resp_ok.json()["estado"] == "aprobada"
