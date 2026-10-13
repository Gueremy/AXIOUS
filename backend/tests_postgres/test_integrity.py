"""Pruebas opt-in contra una BD PostgreSQL migrada; nunca usan SQLite."""
import asyncio
import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.config import settings
from app.core.dependencies_v2 import TenantContext
from app.database import AsyncSessionLocal
from app.models.usuario import Usuario
from app.models.v2 import (
    Item, Lote, MovimientoV2, Organizacion, SaldoStock, Sitio,
    SolicitudMovimiento, TipoMovimiento, Ubicacion, Zona,
)
from app.services.v2.movimiento_service import MovimientoService


def _require_test_postgres():
    if "postgresql+asyncpg" not in settings.DATABASE_URL or "axious_v2_completion_test" not in settings.DATABASE_URL:
        pytest.skip("Requiere DATABASE_URL de PostgreSQL axious_v2_completion_test")


@pytest.mark.asyncio(loop_scope="session")
async def test_v2_documentos_jsonb_y_migracion_final():
    _require_test_postgres()
    async with AsyncSessionLocal() as db:
        revision = (await db.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
        assert revision == "b4c5d6e7f809"
        columns = (await db.execute(text("""
            SELECT table_name, column_name, data_type FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name LIKE 'v2_%'
              AND column_name IN ('atributos', 'configuracion', 'layout', 'datos_crudos', 'mapeo')
        """))).all()
        assert len(columns) >= 10
        assert all(data_type == "jsonb" for _, _, data_type in columns)


@pytest.mark.asyncio(loop_scope="session")
async def test_aprobacion_concurrente_y_constraints_postgres():
    _require_test_postgres()
    org = Organizacion(id=str(uuid.uuid4()), nombre="Prueba transaccional", slug=f"pg-{uuid.uuid4().hex[:12]}")
    user = Usuario(id=str(uuid.uuid4()), nombre="Aprobador", email=f"pg-{uuid.uuid4().hex[:12]}@example.cl",
                   password_hash="unused", codigo_empleado=f"PG-{uuid.uuid4().hex[:12]}",
                   rol="super_admin", id_organizacion=org.id, activo=True)
    site = Sitio(id=str(uuid.uuid4()), id_organizacion=org.id, codigo="S", nombre="Sitio", tipo="bodega")
    zone = Zona(id=str(uuid.uuid4()), id_organizacion=org.id, id_sitio=site.id,
                codigo="Z", nombre="Zona", tipo="bodega")
    location = Ubicacion(id=str(uuid.uuid4()), id_organizacion=org.id, id_zona=zone.id,
                         codigo="U", capacidad_maxima=100, unidad_capacidad="kg", ocupacion_actual=0)
    item = Item(id=str(uuid.uuid4()), id_organizacion=org.id, codigo="I", nombre="Item",
                categoria="general", unidad_medida="kg")
    lot = Lote(id=str(uuid.uuid4()), id_organizacion=org.id, id_item=item.id, numero_lote="L")
    kind = TipoMovimiento(id=str(uuid.uuid4()), id_organizacion=org.id, codigo="ING",
                          nombre="Ingreso", efecto_stock="entrada", requiere_destino=True, requiere_aprobacion=True)
    request = SolicitudMovimiento(id=str(uuid.uuid4()), id_organizacion=org.id,
                                  id_tipo_movimiento=kind.id, id_item=item.id, id_lote=lot.id,
                                  id_ubicacion_destino=location.id, id_usuario_solicitante=user.id,
                                  cantidad=Decimal("10"), unidad_medida="kg", estado="pendiente", atributos={})
    async with AsyncSessionLocal() as db:
        db.add(org)
        await db.flush()
        db.add_all([user, site, item, kind])
        await db.flush()
        db.add_all([zone, lot])
        await db.flush()
        db.add(location)
        await db.flush()
        db.add(request)
        await db.commit()

    tenant = TenantContext(user, org, "super_admin", {"movimiento:approve"}, None)

    async def approve():
        async with AsyncSessionLocal() as db:
            return await MovimientoService.aprobar_solicitud(db, tenant, request.id)

    outcomes = await asyncio.gather(approve(), approve(), return_exceptions=True)
    assert sum(isinstance(outcome, MovimientoV2) for outcome in outcomes) == 1
    assert sum(isinstance(outcome, HTTPException) and outcome.status_code == 400 for outcome in outcomes) == 1

    async with AsyncSessionLocal() as db:
        movements = (await db.execute(select(MovimientoV2).where(MovimientoV2.id_solicitud == request.id))).scalars().all()
        assert len(movements) == 1
        assert movements[0].id_usuario_aprobador == user.id
        balance = (await db.execute(select(SaldoStock).where(SaldoStock.id_ubicacion == location.id))).scalar_one()
        assert balance.cantidad == Decimal("10")

        with pytest.raises(DBAPIError):
            await db.execute(update(MovimientoV2).where(MovimientoV2.id == movements[0].id).values(cantidad=11))
        await db.rollback()

    async with AsyncSessionLocal() as db:
        db.add(MovimientoV2(id_organizacion=org.id, id_solicitud=request.id, id_tipo_movimiento=kind.id,
                            id_item=item.id, id_usuario=user.id, cantidad=1, unidad_medida="kg", efecto_stock="entrada"))
        with pytest.raises(IntegrityError):
            await db.flush()
        await db.rollback()

    async with AsyncSessionLocal() as db:
        db.add(SaldoStock(id_organizacion=org.id, id_ubicacion=location.id,
                          id_item=item.id, id_lote=None, cantidad=0, unidad_medida="kg"))
        await db.commit()
    async with AsyncSessionLocal() as db:
        db.add(SaldoStock(id_organizacion=org.id, id_ubicacion=location.id,
                          id_item=item.id, id_lote=None, cantidad=0, unidad_medida="kg"))
        with pytest.raises(IntegrityError):
            await db.flush()
        await db.rollback()
