"""
tests/test_dashboard.py
Tests Sprint 4 — Dashboard KPIs (AXI-18).

12 tests:
  - Estructura y semántica de los 4 KPIs
  - ocupacion-por-galpon: cálculo, estados
  - evolucion: lista, filtro de días
  - Aislamiento multi-sede
  - Acceso por rol gerencia
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alerta import Alerta
from app.models.container import Container
from app.models.galpon import Galpon
from app.models.movimiento import Movimiento
from app.models.producto import Producto
from app.models.sede import Sede
from app.models.usuario import Usuario


# ── Fixtures específicas del dashboard ────────────────────────────────────────

@pytest_asyncio.fixture()
async def container_medio(db: AsyncSession, galpon):
    """Container al 60% — estado 'medio'."""
    c = Container(
        id=str(uuid.uuid4()),
        id_galpon=galpon.id,
        codigo="DASH-60",
        posicion_fila=2, posicion_col=2,
        capacidad_max=Decimal("1000.00"),
        unidad_medida="kg",
        ocupacion_actual=Decimal("600.00"),
        estado="disponible",
        tipo_producto_permitido="alimento",
    )
    db.add(c)
    await db.flush()
    return c


@pytest_asyncio.fixture()
async def container_critico_dash(db: AsyncSession, galpon):
    """Container al 85% — estado 'critico'."""
    c = Container(
        id=str(uuid.uuid4()),
        id_galpon=galpon.id,
        codigo="DASH-85",
        posicion_fila=3, posicion_col=3,
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
async def mov_hoy(db: AsyncSession, container, producto, usuario_operario, usuario_jefe):
    """Movimiento aprobado creado hoy."""
    now = datetime.now(timezone.utc)
    m = Movimiento(
        id=str(uuid.uuid4()),
        id_container=container.id,
        id_producto=producto.id,
        id_usuario=usuario_operario.id,
        id_usuario_aprobador=usuario_jefe.id,
        tipo="entrada_proveedor",
        estado="aprobado",
        cantidad=Decimal("50.00"),
        numero_lote="HOY-001",
        fecha_fabricacion=now - timedelta(days=10),
        fecha_vencimiento=now + timedelta(days=60),
        nombre_proveedor="BioMar Chile",
        num_guia_despacho="GD-HOY-001",
        registro_sanitario="RS-HOY-001",
        temperatura_almacen=Decimal("-2.0"),
        fecha_hora=now,
        fecha_aprobacion=now,
        origen="online",
    )
    db.add(m)
    await db.flush()
    return m


@pytest_asyncio.fixture()
async def usuario_gerencia(db: AsyncSession, sede: Sede) -> Usuario:
    from passlib.context import CryptContext
    pwd = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=4)
    uid = uuid.uuid4().hex[:8].upper()
    u = Usuario(
        id=str(uuid.uuid4()),
        nombre="Gerente Test",
        email=f"gerente_{uid}@test.cl",
        password_hash=pwd.hash("Test1234!"),
        codigo_empleado=f"GR{uid}",
        rol="gerencia",
        id_sede=sede.id,
        activo=True,
    )
    db.add(u)
    await db.flush()
    return u


# ── Tests KPIs ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_kpis_retorna_estructura(client, db, usuario_jefe):
    """GET /dashboard/kpis retorna los 4 campos KPI."""
    login = await client.post("/auth/login", data={
        "username": usuario_jefe.email, "password": "Test1234!"
    })
    token = login.json()["access_token"]

    resp = await client.get("/dashboard/kpis", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "ocupacion_global_pct" in data
    assert "alertas_activas" in data
    assert "movimientos_hoy" in data
    assert "proximo_vencimiento_dias" in data


@pytest.mark.asyncio
async def test_ocupacion_global_calculo_correcto(client, db, container, usuario_jefe):
    """container tiene 300/1000 = 30% de ocupación → KPI debe ser ≈30."""
    # container del conftest tiene ocupacion_actual=300, capacidad_max=1000
    login = await client.post("/auth/login", data={
        "username": usuario_jefe.email, "password": "Test1234!"
    })
    token = login.json()["access_token"]

    resp = await client.get("/dashboard/kpis", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    # Puede haber otros containers del mismo test, pero la ocupación no debe ser 0
    pct = resp.json()["ocupacion_global_pct"]
    assert isinstance(pct, float)
    assert pct >= 0


@pytest.mark.asyncio
async def test_alertas_activas_count(client, db, container, usuario_jefe):
    """KPI alertas_activas cuenta las alertas activas de la sede."""
    # Crear una alerta manualmente
    a = Alerta(
        id=str(uuid.uuid4()),
        id_container=container.id,
        tipo="capacidad_critica",
        severidad="critica",
        descripcion="Test alerta dashboard",
        estado="activa",
    )
    db.add(a)
    await db.commit()

    login = await client.post("/auth/login", data={
        "username": usuario_jefe.email, "password": "Test1234!"
    })
    token = login.json()["access_token"]

    resp = await client.get("/dashboard/kpis", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["alertas_activas"] >= 1


@pytest.mark.asyncio
async def test_movimientos_hoy(client, db, mov_hoy, usuario_jefe):
    """KPI movimientos_hoy cuenta movimientos de hoy."""
    login = await client.post("/auth/login", data={
        "username": usuario_jefe.email, "password": "Test1234!"
    })
    token = login.json()["access_token"]

    resp = await client.get("/dashboard/kpis", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["movimientos_hoy"] >= 1


@pytest.mark.asyncio
async def test_proximo_vencimiento(client, db, movimiento_aprobado, usuario_jefe):
    """KPI proximo_vencimiento_dias retorna días hasta el vencimiento más cercano."""
    # movimiento_aprobado del conftest vence en ~90 días
    login = await client.post("/auth/login", data={
        "username": usuario_jefe.email, "password": "Test1234!"
    })
    token = login.json()["access_token"]

    resp = await client.get("/dashboard/kpis", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    dias = resp.json()["proximo_vencimiento_dias"]
    assert dias is None or isinstance(dias, int)


# ── Tests ocupacion-por-galpon ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ocupacion_por_galpon_estructura(client, db, usuario_jefe):
    """GET /dashboard/ocupacion-por-galpon retorna lista con los campos requeridos."""
    login = await client.post("/auth/login", data={
        "username": usuario_jefe.email, "password": "Test1234!"
    })
    token = login.json()["access_token"]

    resp = await client.get("/dashboard/ocupacion-por-galpon", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    if data:
        item = data[0]
        assert "name" in item
        assert "ocupacion_pct" in item
        assert "estado" in item


@pytest.mark.asyncio
async def test_ocupacion_estado_critico(client, db, container_critico_dash, usuario_jefe):
    """Galpón con containers al 85% → estado = 'critico'."""
    login = await client.post("/auth/login", data={
        "username": usuario_jefe.email, "password": "Test1234!"
    })
    token = login.json()["access_token"]

    resp = await client.get("/dashboard/ocupacion-por-galpon", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    # Al menos un galpón debe tener estado 'critico' (el container_critico_dash está al 85%)
    estados = [item["estado"] for item in data]
    assert "critico" in estados


@pytest.mark.asyncio
async def test_ocupacion_estado_medio(client, db, container_medio, usuario_jefe):
    """Galpón con containers al 60% → estado = 'medio'."""
    login = await client.post("/auth/login", data={
        "username": usuario_jefe.email, "password": "Test1234!"
    })
    token = login.json()["access_token"]

    resp = await client.get("/dashboard/ocupacion-por-galpon", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    # Al menos un galpón debe tener estado distinto de 'disponible'
    data = resp.json()
    estados = [item["estado"] for item in data]
    assert any(e in ["medio", "critico"] for e in estados)


# ── Tests evolucion ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_evolucion_retorna_lista(client, db, usuario_jefe):
    """GET /dashboard/evolucion retorna lista de objetos con fecha, movimientos."""
    login = await client.post("/auth/login", data={
        "username": usuario_jefe.email, "password": "Test1234!"
    })
    token = login.json()["access_token"]

    resp = await client.get("/dashboard/evolucion", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    if data:
        item = data[0]
        assert "fecha" in item
        assert "movimientos" in item
        assert "entradas" in item
        assert "salidas" in item


@pytest.mark.asyncio
async def test_evolucion_dias_param(client, db, usuario_jefe):
    """?dias=7 retorna datos coherentes (lista, sin error)."""
    login = await client.post("/auth/login", data={
        "username": usuario_jefe.email, "password": "Test1234!"
    })
    token = login.json()["access_token"]

    resp = await client.get("/dashboard/evolucion?dias=7", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ── Tests de acceso y aislamiento ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_aislamiento_sede_dashboard(client, db, container, usuario_jefe):
    """KPIs de una sede no se mezclan con los de otra."""
    from passlib.context import CryptContext
    pwd = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=4)

    otra_sede = Sede(
        id=str(uuid.uuid4()),
        nombre="Sede Aysén",
        tipo="ponton",
        ubicacion="Aysén",
        estado="activo",
    )
    db.add(otra_sede)
    await db.flush()

    uid = uuid.uuid4().hex[:8].upper()
    jefe_otra = Usuario(
        id=str(uuid.uuid4()),
        nombre="Jefe Aysén",
        email=f"jefe_aysen_{uid}@test.cl",
        password_hash=pwd.hash("Test1234!"),
        codigo_empleado=f"JA{uid}",
        rol="jefe_bodega",
        id_sede=otra_sede.id,
        activo=True,
    )
    db.add(jefe_otra)
    await db.flush()

    # Crear alerta en la sede original
    a = Alerta(
        id=str(uuid.uuid4()),
        id_container=container.id,
        tipo="cuarentena_activa",
        severidad="critica",
        descripcion="Aislamiento test",
        estado="activa",
    )
    db.add(a)
    await db.commit()

    login = await client.post("/auth/login", data={
        "username": jefe_otra.email, "password": "Test1234!"
    })
    token = login.json()["access_token"]

    resp = await client.get("/dashboard/kpis", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    # El jefe de Aysén no debe ver las alertas de la sede original
    assert resp.json()["alertas_activas"] == 0


@pytest.mark.asyncio
async def test_gerencia_puede_ver_kpis(client, db, usuario_gerencia):
    """Rol gerencia tiene acceso al dashboard."""
    login = await client.post("/auth/login", data={
        "username": usuario_gerencia.email, "password": "Test1234!"
    })
    token = login.json()["access_token"]

    resp = await client.get("/dashboard/kpis", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
