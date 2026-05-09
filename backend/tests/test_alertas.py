"""
tests/test_alertas.py
Tests Sprint 3 — Motor de alertas (AXI-14) + Router CRUD (AXI-17).

13 tests:
  - 8 tipos de alerta (generación correcta)
  - Deduplicación
  - Endpoints CRUD (activas, revisar, resolver)
  - Aislamiento multi-sede
  - Control de acceso por rol
"""
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alerta import Alerta
from app.models.container import Container
from app.models.galpon import Galpon
from app.models.movimiento import Movimiento
from app.models.producto import Producto
from app.models.sede import Sede
from app.models.usuario import Usuario
from app.services.alertas import evaluar_alertas


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture()
async def container_critico(db: AsyncSession, galpon):
    """Container al 85% de capacidad — debe disparar capacidad_critica."""
    c = Container(
        id=str(uuid.uuid4()),
        id_galpon=galpon.id,
        codigo="CRIT-01",
        posicion_fila=2,
        posicion_col=2,
        capacidad_max=Decimal("1000.00"),
        unidad_medida="kg",
        ocupacion_actual=Decimal("850.00"),
        estado="disponible",
        tipo_producto_permitido="alimento",
    )
    db.add(c)
    await db.flush()
    return c


@pytest_asyncio.fixture()
async def container_normal(db: AsyncSession, galpon):
    """Container al 50% — NO debe disparar capacidad_critica."""
    c = Container(
        id=str(uuid.uuid4()),
        id_galpon=galpon.id,
        codigo="NORM-01",
        posicion_fila=3,
        posicion_col=3,
        capacidad_max=Decimal("1000.00"),
        unidad_medida="kg",
        ocupacion_actual=Decimal("500.00"),
        estado="disponible",
        tipo_producto_permitido="alimento",
    )
    db.add(c)
    await db.flush()
    return c


@pytest_asyncio.fixture()
async def container_cuarentena(db: AsyncSession, galpon):
    """Container en cuarentena."""
    c = Container(
        id=str(uuid.uuid4()),
        id_galpon=galpon.id,
        codigo="QUAR-01",
        posicion_fila=4,
        posicion_col=4,
        capacidad_max=Decimal("500.00"),
        unidad_medida="kg",
        ocupacion_actual=Decimal("200.00"),
        estado="cuarentena",
        tipo_producto_permitido="alimento",
        motivo_estado="Alerta sanitaria SERNAPESCA",
    )
    db.add(c)
    await db.flush()
    return c


@pytest_asyncio.fixture()
async def container_bajo_stock(db: AsyncSession, galpon):
    """Container con stock bajo para test de stock_minimo."""
    c = Container(
        id=str(uuid.uuid4()),
        id_galpon=galpon.id,
        codigo="LOW-01",
        posicion_fila=5,
        posicion_col=5,
        capacidad_max=Decimal("1000.00"),
        unidad_medida="kg",
        ocupacion_actual=Decimal("30.00"),
        estado="disponible",
        tipo_producto_permitido="alimento",
    )
    db.add(c)
    await db.flush()
    return c


@pytest_asyncio.fixture()
async def mov_vence_pronto(db, container, producto, usuario_operario, usuario_jefe):
    """Movimiento aprobado que vence en 5 días."""
    now = datetime.utcnow()
    m = Movimiento(
        id=str(uuid.uuid4()),
        id_container=container.id,
        id_producto=producto.id,
        id_usuario=usuario_operario.id,
        id_usuario_aprobador=usuario_jefe.id,
        tipo="entrada_proveedor",
        estado="aprobado",
        cantidad=Decimal("50.00"),
        numero_lote="VENCE-PRONTO-001",
        fecha_fabricacion=now - timedelta(days=60),
        fecha_vencimiento=now + timedelta(days=5),
        nombre_proveedor="BioMar Chile",
        num_guia_despacho="GD-VENCE-001",
        registro_sanitario="RS-VENCE-001",
        temperatura_almacen=Decimal("-2.0"),
        fecha_hora=now,
        fecha_aprobacion=now,
        origen="online",
    )
    db.add(m)
    await db.flush()
    return m


@pytest_asyncio.fixture()
async def mov_vence_30(db, container, producto, usuario_operario, usuario_jefe):
    """Movimiento aprobado que vence en 20 días (dentro del rango de 30 días)."""
    now = datetime.utcnow()
    m = Movimiento(
        id=str(uuid.uuid4()),
        id_container=container.id,
        id_producto=producto.id,
        id_usuario=usuario_operario.id,
        id_usuario_aprobador=usuario_jefe.id,
        tipo="entrada_proveedor",
        estado="aprobado",
        cantidad=Decimal("50.00"),
        numero_lote="VENCE-30D-001",
        fecha_fabricacion=now - timedelta(days=60),
        fecha_vencimiento=now + timedelta(days=20),
        nombre_proveedor="BioMar Chile",
        num_guia_despacho="GD-VENCE30-001",
        registro_sanitario="RS-VENCE30-001",
        temperatura_almacen=Decimal("-2.0"),
        fecha_hora=now,
        fecha_aprobacion=now,
        origen="online",
    )
    db.add(m)
    await db.flush()
    return m


@pytest_asyncio.fixture()
async def mov_stock_bajo(db, container_bajo_stock, producto, usuario_operario, usuario_jefe):
    """Movimiento aprobado para container con stock bajo."""
    now = datetime.utcnow()
    m = Movimiento(
        id=str(uuid.uuid4()),
        id_container=container_bajo_stock.id,
        id_producto=producto.id,
        id_usuario=usuario_operario.id,
        id_usuario_aprobador=usuario_jefe.id,
        tipo="entrada_proveedor",
        estado="aprobado",
        cantidad=Decimal("30.00"),
        numero_lote="LOW-STOCK-001",
        fecha_fabricacion=now - timedelta(days=30),
        fecha_vencimiento=now + timedelta(days=180),
        nombre_proveedor="BioMar Chile",
        num_guia_despacho="GD-LOW-001",
        registro_sanitario="RS-LOW-001",
        temperatura_almacen=Decimal("-2.0"),
        fecha_hora=now,
        fecha_aprobacion=now,
        origen="online",
    )
    db.add(m)
    await db.flush()
    return m


# ── Tests del Motor de Alertas (AXI-14) ──────────────────────────────────────

@pytest.mark.asyncio
async def test_capacidad_critica_se_genera(db, container_critico):
    """Container al 85% → debe generar alerta capacidad_critica."""
    alertas = await evaluar_alertas(container_critico.id, db)
    tipos = [a.tipo for a in alertas]
    assert "capacidad_critica" in tipos


@pytest.mark.asyncio
async def test_capacidad_normal_sin_alerta(db, container_normal):
    """Container al 50% → NO debe generar alerta capacidad_critica."""
    alertas = await evaluar_alertas(container_normal.id, db)
    tipos = [a.tipo for a in alertas]
    assert "capacidad_critica" not in tipos


@pytest.mark.asyncio
async def test_vencimiento_7_dias_se_genera(db, container, mov_vence_pronto):
    """Movimiento que vence en 5 días → alerta vencimiento_7_dias."""
    alertas = await evaluar_alertas(container.id, db)
    tipos = [a.tipo for a in alertas]
    assert "vencimiento_7_dias" in tipos


@pytest.mark.asyncio
async def test_vencimiento_30_dias_se_genera(db, container, mov_vence_30):
    """Movimiento que vence en 20 días → alerta vencimiento_30_dias."""
    alertas = await evaluar_alertas(container.id, db)
    tipos = [a.tipo for a in alertas]
    assert "vencimiento_30_dias" in tipos


@pytest.mark.asyncio
async def test_stock_minimo_se_genera(db, container_bajo_stock, mov_stock_bajo):
    """Ocupación 30kg con stock_minimo=50kg → alerta stock_minimo."""
    # producto fixture tiene stock_minimo=50.00
    alertas = await evaluar_alertas(container_bajo_stock.id, db)
    tipos = [a.tipo for a in alertas]
    assert "stock_minimo" in tipos


@pytest.mark.asyncio
async def test_fuera_horario_se_genera(db, container):
    """Llamar con hora 23:00 → alerta movimiento_fuera_horario."""
    hora_noche = datetime(2026, 5, 15, 23, 30, 0)
    alertas = await evaluar_alertas(container.id, db, ahora=hora_noche)
    tipos = [a.tipo for a in alertas]
    assert "movimiento_fuera_horario" in tipos


@pytest.mark.asyncio
async def test_cuarentena_activa_se_genera(db, container_cuarentena):
    """Container en cuarentena → alerta cuarentena_activa."""
    alertas = await evaluar_alertas(container_cuarentena.id, db)
    tipos = [a.tipo for a in alertas]
    assert "cuarentena_activa" in tipos


@pytest.mark.asyncio
async def test_deduplicacion(db, container_critico):
    """Evaluar 2 veces seguidas → solo 1 alerta (no duplicada)."""
    alertas1 = await evaluar_alertas(container_critico.id, db)
    alertas2 = await evaluar_alertas(container_critico.id, db)

    # La segunda evaluación no debe crear alertas de capacidad_critica
    tipos2_capacidad = [a for a in alertas2 if a.tipo == "capacidad_critica"]
    assert len(tipos2_capacidad) == 0

    # Verificar que solo hay 1 alerta de capacidad en total
    total = await db.scalar(
        select(func.count()).select_from(Alerta).where(
            Alerta.id_container == container_critico.id,
            Alerta.tipo == "capacidad_critica",
            Alerta.estado == "activa",
        )
    )
    assert total == 1


# ── Tests del Router CRUD (AXI-17) ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_alertas_activas(client, db, container_critico, usuario_jefe):
    """GET /alertas/activas retorna alertas activas de la sede."""
    # Primero generar una alerta
    await evaluar_alertas(container_critico.id, db)

    # Login como jefe
    login_resp = await client.post("/auth/login", data={
        "username": usuario_jefe.email, "password": "Test1234!"
    })
    token = login_resp.json()["access_token"]

    resp = await client.get(
        "/alertas/activas",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert data[0]["estado"] == "activa"


@pytest.mark.asyncio
async def test_aislamiento_sede_alertas(client, db, container_critico, galpon, sede):
    """Jefe de otra sede no ve las alertas."""
    # Crear alerta en sede original
    await evaluar_alertas(container_critico.id, db)

    # Crear otra sede y un jefe para ella
    otra_sede = Sede(
        id=str(uuid.uuid4()),
        nombre="Sede Aislada",
        tipo="planta",
        ubicacion="Aysén",
        estado="activo",
    )
    db.add(otra_sede)
    await db.flush()

    from passlib.context import CryptContext
    pwd = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=4)
    uid = uuid.uuid4().hex[:8].upper()
    jefe_otra = Usuario(
        id=str(uuid.uuid4()),
        nombre="Jefe Otra Sede",
        email=f"jefe_otra_{uid}@test.cl",
        password_hash=pwd.hash("Test1234!"),
        codigo_empleado=f"JO{uid}",
        rol="jefe_bodega",
        id_sede=otra_sede.id,
        activo=True,
    )
    db.add(jefe_otra)
    await db.flush()

    # Login con el jefe de la otra sede
    login_resp = await client.post("/auth/login", data={
        "username": jefe_otra.email, "password": "Test1234!"
    })
    token = login_resp.json()["access_token"]

    resp = await client.get(
        "/alertas/activas",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    data = resp.json()
    # No debería ver alertas de la otra sede
    assert len(data) == 0


@pytest.mark.asyncio
async def test_patch_revisar(client, db, container_critico, usuario_jefe):
    """PATCH /alertas/{id}/revisar cambia estado activa → revisada."""
    alertas = await evaluar_alertas(container_critico.id, db)
    assert len(alertas) >= 1
    alerta_id = alertas[0].id

    login_resp = await client.post("/auth/login", data={
        "username": usuario_jefe.email, "password": "Test1234!"
    })
    token = login_resp.json()["access_token"]

    resp = await client.patch(
        f"/alertas/{alerta_id}/revisar",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["estado"] == "revisada"
    assert resp.json()["id_usuario_revision"] is not None


@pytest.mark.asyncio
async def test_patch_resolver(client, db, container_critico, usuario_jefe):
    """PATCH /alertas/{id}/resolver cambia estado revisada → resuelta."""
    alertas = await evaluar_alertas(container_critico.id, db)
    assert len(alertas) >= 1
    alerta = alertas[0]

    # Primero revisar
    alerta.estado = "revisada"
    alerta.id_usuario_revision = usuario_jefe.id
    alerta.fecha_revision = datetime.utcnow()
    await db.commit()
    await db.refresh(alerta)

    login_resp = await client.post("/auth/login", data={
        "username": usuario_jefe.email, "password": "Test1234!"
    })
    token = login_resp.json()["access_token"]

    resp = await client.patch(
        f"/alertas/{alerta.id}/resolver",
        headers={"Authorization": f"Bearer {token}"},
        json={"observacion": "Producto reubicado."}
    )
    assert resp.status_code == 200
    assert resp.json()["estado"] == "resuelta"


@pytest.mark.asyncio
async def test_operario_no_puede_ver_alertas(client, db, usuario_operario):
    """Operario → 403 al intentar ver alertas."""
    login_resp = await client.post("/auth/login", data={
        "username": usuario_operario.email, "password": "Test1234!"
    })
    token = login_resp.json()["access_token"]

    resp = await client.get(
        "/alertas/activas",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 403
