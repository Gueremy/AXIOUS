"""
tests/v2/test_1g_bi_readonly.py
Pruebas de la interfaz de sólo lectura para Business Intelligence (Fase 1G):
- Disponibilidad de dimensiones (sitios, items) y tablas de hechos (stock, movimientos, inconsistencias).
- Sólo lectura estricta: métodos de mutación (POST, DELETE) son rechazados.
- Protección de datos personales (Ley 19.628): no se expone RUT ni contraseñas.
- Consistencia analítica: métricas de existencias coinciden con el inventario real.
- Aislamiento multi-tenant estricto.
"""
from decimal import Decimal
import uuid
import pytest
from httpx import AsyncClient

from app.core.security import create_access_token
from app.models.usuario import Usuario
from app.models.v2 import (
    Organizacion, Sitio, Zona, Ubicacion,
    Item, Lote, SaldoStock, TipoMovimiento, MovimientoV2
)


@pytest.fixture
async def setup_bi_fixture(db):
    """Crea un dataset analítico completo en Organización A y B."""
    # Org A
    org_a = Organizacion(id=str(uuid.uuid4()), nombre="Logística BI A", slug=f"bi-a-{uuid.uuid4().hex[:4]}")
    db.add(org_a)
    await db.flush()

    user_a = Usuario(
        id=str(uuid.uuid4()),
        nombre="Analista Power BI A",
        email=f"bi_a_{uuid.uuid4().hex[:4]}@bi.cl",
        password_hash="secret_hash_never_exposed",
        codigo_empleado=f"EMP-BI-A-{uuid.uuid4().hex[:6]}",
        rol="super_admin",
        id_organizacion=org_a.id,
        activo=True,
    )
    db.add(user_a)
    await db.flush()

    sitio_a = Sitio(id=str(uuid.uuid4()), id_organizacion=org_a.id, codigo="SIT-BI-01", nombre="Centro Logístico BI", tipo="bodega")
    db.add(sitio_a)
    await db.flush()

    zona_a = Zona(id=str(uuid.uuid4()), id_organizacion=org_a.id, id_sitio=sitio_a.id, codigo="ZON-BI-A", nombre="Sector Racks", tipo="sector")
    db.add(zona_a)
    await db.flush()

    ubi_a = Ubicacion(
        id=str(uuid.uuid4()),
        id_organizacion=org_a.id,
        id_zona=zona_a.id,
        codigo="BIN-BI-101",
        capacidad_maxima=Decimal("5000.0000"),
        unidad_capacidad="kg",
        ocupacion_actual=Decimal("1250.0000"),
    )
    db.add(ubi_a)
    await db.flush()

    item_a = Item(
        id=str(uuid.uuid4()),
        id_organizacion=org_a.id,
        codigo="SKU-BI-FISH",
        nombre="Salmón Congelado Premium",
        categoria="pescado",
        unidad_medida="kg",
    )
    db.add(item_a)
    await db.flush()

    lote_a = Lote(id=str(uuid.uuid4()), id_organizacion=org_a.id, id_item=item_a.id, numero_lote="LOT-BI-2026")
    db.add(lote_a)
    await db.flush()

    saldo_a = SaldoStock(
        id_organizacion=org_a.id,
        id_ubicacion=ubi_a.id,
        id_item=item_a.id,
        id_lote=lote_a.id,
        cantidad=Decimal("1250.0000"),
        unidad_medida="kg",
    )
    db.add(saldo_a)
    await db.flush()

    tipo_in = TipoMovimiento(
        id=str(uuid.uuid4()),
        id_organizacion=org_a.id,
        codigo="RECEPCION",
        nombre="Recepción de Planta",
        efecto_stock="entrada",
        requiere_destino=True,
        requiere_aprobacion=False,
    )
    db.add(tipo_in)
    await db.flush()

    mov_a = MovimientoV2(
        id=str(uuid.uuid4()),
        id_organizacion=org_a.id,
        id_tipo_movimiento=tipo_in.id,
        id_item=item_a.id,
        id_lote=lote_a.id,
        id_ubicacion_destino=ubi_a.id,
        id_usuario=user_a.id,
        cantidad=Decimal("1250.0000"),
        unidad_medida="kg",
        efecto_stock="entrada",
        atributos={},
    )
    db.add(mov_a)
    await db.flush()

    token_a = create_access_token({"sub": user_a.id, "org_id": org_a.id})

    # Org B (aislada)
    org_b = Organizacion(id=str(uuid.uuid4()), nombre="Logística BI B", slug=f"bi-b-{uuid.uuid4().hex[:4]}")
    db.add(org_b)
    await db.flush()

    user_b = Usuario(
        id=str(uuid.uuid4()),
        nombre="Analista B",
        email=f"bi_b_{uuid.uuid4().hex[:4]}@bi.cl",
        password_hash="secret_b",
        codigo_empleado=f"EMP-BI-B-{uuid.uuid4().hex[:6]}",
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
        "token_a": token_a,
        "user_a": user_a,
        "ubi_a": ubi_a,
        "item_a": item_a,
        "org_b": org_b,
        "token_b": token_b,
    }


@pytest.mark.asyncio
async def test_bi_dimensiones_y_hechos_disponibles(client: AsyncClient, setup_bi_fixture):
    """Verifica que las dimensiones y tablas de hechos entreguen datos estructurados para Power BI."""
    ctx = setup_bi_fixture
    headers = {"Authorization": f"Bearer {ctx['token_a']}"}

    # 1. Dimensión Sitios
    resp_sitios = await client.get("/api/v2/bi/dimensiones/sitios", headers=headers)
    assert resp_sitios.status_code == 200
    sitios = resp_sitios.json()
    assert len(sitios) >= 1
    assert sitios[0]["codigo_sitio"] == "SIT-BI-01"
    assert sitios[0]["total_ubicaciones"] >= 1

    # 2. Dimensión Items
    resp_items = await client.get("/api/v2/bi/dimensiones/items", headers=headers)
    assert resp_items.status_code == 200
    items = resp_items.json()
    assert any(i["codigo_item"] == "SKU-BI-FISH" for i in items)

    # 3. Hechos de Stock
    resp_stock = await client.get("/api/v2/bi/hechos/stock", headers=headers)
    assert resp_stock.status_code == 200
    stock = resp_stock.json()
    assert len(stock) >= 1
    fact_stock = stock[0]
    assert fact_stock["codigo_ubicacion"] == "BIN-BI-101"
    assert Decimal(str(fact_stock["cantidad_saldo"])) == Decimal("1250.0000")
    assert fact_stock["porcentaje_ocupacion"] == 25.0

    # 4. Hechos de Movimientos
    resp_movs = await client.get("/api/v2/bi/hechos/movimientos", headers=headers)
    assert resp_movs.status_code == 200
    movs = resp_movs.json()
    assert len(movs) >= 1
    fact_mov = movs[0]
    assert fact_mov["tipo_movimiento_codigo"] == "RECEPCION"
    assert fact_mov["codigo_item"] == "SKU-BI-FISH"
    assert Decimal(str(fact_mov["cantidad"])) == Decimal("1250.0000")


@pytest.mark.asyncio
async def test_bi_proteccion_datos_personales_ley_19628(client: AsyncClient, setup_bi_fixture):
    """Verifica que en la tabla de hechos de movimientos nunca se exponga RUT ni secretos."""
    ctx = setup_bi_fixture
    headers = {"Authorization": f"Bearer {ctx['token_a']}"}

    resp = await client.get("/api/v2/bi/hechos/movimientos", headers=headers)
    assert resp.status_code == 200
    movs = resp.json()
    for m in movs:
        # Se debe usar código de empleado
        assert "codigo_empleado_operario" in m
        assert m["codigo_empleado_operario"].startswith("EMP-BI-A-")
        # NUNCA RUT ni hashes
        assert "rut" not in m
        assert "password" not in str(m).lower()
        assert "secret_hash" not in str(m).lower()


@pytest.mark.asyncio
async def test_bi_solo_lectura_estricto(client: AsyncClient, setup_bi_fixture):
    """Verifica que los endpoints de BI rechacen métodos de mutación (POST, PUT, DELETE)."""
    ctx = setup_bi_fixture
    headers = {"Authorization": f"Bearer {ctx['token_a']}"}

    resp_post = await client.post("/api/v2/bi/hechos/stock", headers=headers, json={"cantidad": 100})
    assert resp_post.status_code == 405  # Method Not Allowed

    resp_del = await client.delete("/api/v2/bi/dimensiones/sitios", headers=headers)
    assert resp_del.status_code == 405


@pytest.mark.asyncio
async def test_bi_aislamiento_multitenant(client: AsyncClient, setup_bi_fixture):
    """Verifica que Org B no pueda ver las dimensiones ni hechos de Org A."""
    ctx = setup_bi_fixture
    headers_b = {"Authorization": f"Bearer {ctx['token_b']}"}

    # Org B consulta hechos de stock
    resp_b = await client.get("/api/v2/bi/hechos/stock", headers=headers_b)
    assert resp_b.status_code == 200
    assert len(resp_b.json()) == 0

    # Org B consulta hechos de movimientos
    resp_movs_b = await client.get("/api/v2/bi/hechos/movimientos", headers=headers_b)
    assert resp_movs_b.status_code == 200
    assert len(resp_movs_b.json()) == 0
