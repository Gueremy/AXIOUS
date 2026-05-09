"""
tests/conftest.py
Infraestructura de tests: SQLite async in-memory + FastAPI TestClient.

Dependencias adicionales (agregar a requirements.txt o instalar):
    pip install pytest pytest-asyncio httpx aiosqlite

Los tests usan SQLite en memoria — no requieren PostgreSQL.
Para tests de integracion reales contra PostgreSQL ver pytest --help.
"""
import asyncio
import uuid
from datetime import datetime, timedelta
from itertools import count as _count

_emp_counter = _count(1)
from decimal import Decimal
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool
from passlib.context import CryptContext

from app.main import app
from app.database import Base, get_db
from app.models import (
    Sede, Galpon, Container, Producto,
    Usuario, Movimiento,
)

# SQLite async in-memory para tests (no requiere PostgreSQL)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

engine_test = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = async_sessionmaker(
    engine_test, class_=AsyncSession, expire_on_commit=False
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=4)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_db():
    """Crea todas las tablas una vez por sesion de test."""
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture()
async def db() -> AsyncGenerator[AsyncSession, None]:
    """Sesion de BD con rollback automatico despues de cada test."""
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture()
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient con override de BD apuntando a SQLite test."""
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


# ── Fixtures de datos ────────────────────────────────────────────────────────

@pytest_asyncio.fixture()
async def sede(db: AsyncSession) -> Sede:
    s = Sede(
        id=str(uuid.uuid4()),
        nombre="Sede Test",
        tipo="planta",
        ubicacion="Puerto Montt",
        estado="activo",
    )
    db.add(s)
    await db.flush()
    return s


@pytest_asyncio.fixture()
async def galpon(db: AsyncSession, sede: Sede) -> Galpon:
    g = Galpon(
        id=str(uuid.uuid4()),
        id_sede=sede.id,
        nombre="Galpon Test",
        codigo="TST-A",
        filas=5,
        columnas=6,
        estado="activo",
    )
    db.add(g)
    await db.flush()
    return g


@pytest_asyncio.fixture()
async def container(db: AsyncSession, galpon: Galpon) -> Container:
    c = Container(
        id=str(uuid.uuid4()),
        id_galpon=galpon.id,
        codigo="TST-A-01",
        posicion_fila=1,
        posicion_col=1,
        capacidad_max=Decimal("1000.00"),
        unidad_medida="kg",
        ocupacion_actual=Decimal("300.00"),
        estado="disponible",
        tipo_producto_permitido="alimento",
    )
    db.add(c)
    await db.flush()
    return c


@pytest_asyncio.fixture()
async def producto(db: AsyncSession) -> Producto:
    p = Producto(
        id=str(uuid.uuid4()),
        nombre="Alimento Test",
        codigo_barras="ALI00001",
        categoria="alimento",
        unidad_medida="kg",
        stock_minimo=Decimal("50.00"),
        activo=True,
    )
    db.add(p)
    await db.flush()
    return p


@pytest_asyncio.fixture()
async def usuario_operario(db: AsyncSession, sede: Sede) -> Usuario:
    uid = uuid.uuid4().hex[:8].upper()
    u = Usuario(
        id=str(uuid.uuid4()),
        nombre="Operario Test",
        email=f"operario_{uid}@test.cl",
        password_hash=pwd_context.hash("Test1234!"),
        codigo_empleado=f"OP{uid}",
        rol="operario",
        id_sede=sede.id,
        activo=True,
    )
    db.add(u)
    await db.flush()
    return u


@pytest_asyncio.fixture()
async def usuario_jefe(db: AsyncSession, sede: Sede) -> Usuario:
    uid = uuid.uuid4().hex[:8].upper()
    u = Usuario(
        id=str(uuid.uuid4()),
        nombre="Jefe Test",
        email=f"jefe_{uid}@test.cl",
        password_hash=pwd_context.hash("Test1234!"),
        codigo_empleado=f"JB{uid}",
        rol="jefe_bodega",
        id_sede=sede.id,
        activo=True,
    )
    db.add(u)
    await db.flush()
    return u


@pytest_asyncio.fixture()
async def usuario_admin(db: AsyncSession, sede: Sede) -> Usuario:
    uid = uuid.uuid4().hex[:8].upper()
    u = Usuario(
        id=str(uuid.uuid4()),
        nombre="Admin Test",
        email=f"admin_{uid}@test.cl",
        password_hash=pwd_context.hash("Test1234!"),
        codigo_empleado=f"SA{uid}",
        rol="super_admin",
        id_sede=sede.id,
        activo=True,
    )
    db.add(u)
    await db.flush()
    return u


@pytest_asyncio.fixture()
async def movimiento_aprobado(
    db: AsyncSession,
    container: Container,
    producto: Producto,
    usuario_operario: Usuario,
    usuario_jefe: Usuario,
) -> Movimiento:
    now = datetime.utcnow()
    m = Movimiento(
        id=str(uuid.uuid4()),
        id_container=container.id,
        id_producto=producto.id,
        id_usuario=usuario_operario.id,
        id_usuario_aprobador=usuario_jefe.id,
        tipo="entrada_proveedor",
        estado="aprobado",
        cantidad=Decimal("100.00"),
        numero_lote="LOT-0001-SKR",
        fecha_fabricacion=now - timedelta(days=30),
        fecha_vencimiento=now + timedelta(days=90),
        nombre_proveedor="BioMar Chile",
        num_guia_despacho="GD-10001",
        registro_sanitario="RS-1001",
        temperatura_almacen=Decimal("-2.5"),
        fecha_hora=now,
        fecha_aprobacion=now,
        origen="online",
    )
    db.add(m)
    await db.flush()
    return m
