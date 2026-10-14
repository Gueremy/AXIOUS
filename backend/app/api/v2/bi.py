"""
app/api/v2/bi.py
API REST de sólo lectura para Business Intelligence (Power BI, Metabase, Tableau) — Fase 1G.
- Endpoints puramente de lectura (GET).
- Aislamiento multi-tenant por organización.
- Cumple Ley 19.628: no expone RUT, hashes ni contraseñas.
"""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies_v2 import TenantContext, get_current_tenant, require_permission
from app.core.modules.registry import ModuleRegistry
from app.core.site_access import allowed_location_ids, scope_movement_query
from app.database import get_db
from app.models.usuario import Usuario
from app.models.v2.item import Item
from app.models.v2.lote import Lote
from app.models.v2.movimiento import MovimientoV2
from app.models.v2.saldo_stock import SaldoStock
from app.models.v2.sitio import Sitio
from app.models.v2.tipo_movimiento import TipoMovimiento
from app.models.v2.ubicacion import Ubicacion
from app.models.v2.zona import Zona
from app.schemas.v2.bi import (
    BIInconsistenciaFact,
    BIItemDimension,
    BIMovimientoFact,
    BISitioDimension,
    BIStockFact,
)

router = APIRouter(prefix="/bi", tags=["V2 - Business Intelligence (Read-Only)"],
                   dependencies=[Depends(require_permission("dashboard:read"))])


# ─── Dimensiones ─────────────────────────────────────────────────────────────

@router.get("/dimensiones/sitios", response_model=List[BISitioDimension])
async def obtener_dimension_sitios(
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Retorna dimensión de sitios y resumen estructural para modelado en Power BI / BI."""
    stmt = (
        select(
            Sitio.id,
            Sitio.codigo,
            Sitio.nombre,
            Sitio.tipo,
            func.count(func.distinct(Zona.id)).label("total_zonas"),
            func.count(func.distinct(Ubicacion.id)).label("total_ubicaciones"),
            func.coalesce(func.sum(Ubicacion.capacidad_maxima), 0).label("capacidad_total"),
        )
        .outerjoin(Zona, Sitio.id == Zona.id_sitio)
        .outerjoin(Ubicacion, Zona.id == Ubicacion.id_zona)
        .where(Sitio.id_organizacion == tenant.id_organizacion, Sitio.activo == True)
        .group_by(Sitio.id, Sitio.codigo, Sitio.nombre, Sitio.tipo)
        .order_by(Sitio.codigo.asc())
    )
    if tenant.sitios_permitidos is not None:
        stmt = stmt.where(Sitio.id.in_(tenant.sitios_permitidos))
    res = await db.execute(stmt)
    items = []
    for s_id, s_cod, s_nom, s_tip, tot_z, tot_u, cap_tot in res.all():
        items.append(
            BISitioDimension(
                id_sitio=s_id,
                codigo_sitio=s_cod,
                nombre_sitio=s_nom,
                tipo_sitio=s_tip,
                total_zonas=tot_z,
                total_ubicaciones=tot_u,
                capacidad_total=Decimal(str(cap_tot)),
            )
        )
    return items


@router.get("/dimensiones/items", response_model=List[BIItemDimension])
async def obtener_dimension_items(
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Retorna dimensión de catálogo de ítems para cruce analítico."""
    stmt = (
        select(Item)
        .where(Item.id_organizacion == tenant.id_organizacion)
        .order_by(Item.codigo.asc())
    )
    res = await db.execute(stmt)
    return [
        BIItemDimension(
            id_item=i.id,
            codigo_item=i.codigo,
            nombre_item=i.nombre,
            categoria=i.categoria,
            unidad_medida=i.unidad_medida,
            activo=i.activo,
        )
        for i in res.scalars().all()
    ]


# ─── Tablas de Hechos (Fact Tables) ──────────────────────────────────────────

@router.get("/hechos/stock", response_model=List[BIStockFact])
async def obtener_hechos_stock(
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Retorna la tabla de hechos de existencias y saldos consolidados por ubicación."""
    stmt = (
        select(
            SaldoStock,
            Ubicacion.codigo.label("ubi_codigo"),
            Ubicacion.capacidad_maxima,
            Ubicacion.ocupacion_actual,
            Zona.id_sitio,
            Sitio.codigo.label("sitio_codigo"),
            Item.codigo.label("item_codigo"),
            Lote.numero_lote,
        )
        .join(Ubicacion, SaldoStock.id_ubicacion == Ubicacion.id)
        .join(Zona, Ubicacion.id_zona == Zona.id)
        .join(Sitio, Zona.id_sitio == Sitio.id)
        .join(Item, SaldoStock.id_item == Item.id)
        .outerjoin(Lote, SaldoStock.id_lote == Lote.id)
        .where(SaldoStock.id_organizacion == tenant.id_organizacion)
        .order_by(Ubicacion.codigo.asc())
    )
    if tenant.sitios_permitidos is not None:
        stmt = stmt.where(SaldoStock.id_ubicacion.in_(allowed_location_ids(tenant)))
    res = await db.execute(stmt)
    facts = []
    for saldo, u_cod, cap_max, ocup_act, sit_id, sit_cod, it_cod, num_lot in res.all():
        pct = float((ocup_act / cap_max * 100)) if cap_max > 0 else 0.0
        facts.append(
            BIStockFact(
                id_ubicacion=saldo.id_ubicacion,
                codigo_ubicacion=u_cod,
                id_sitio=sit_id,
                codigo_sitio=sit_cod,
                id_item=saldo.id_item,
                codigo_item=it_cod,
                id_lote=saldo.id_lote,
                numero_lote=num_lot,
                cantidad_saldo=saldo.cantidad,
                unidad_medida=saldo.unidad_medida,
                capacidad_maxima=cap_max,
                ocupacion_actual=ocup_act,
                porcentaje_ocupacion=round(pct, 2),
                fecha_actualizacion=saldo.fecha_actualizacion,
            )
        )
    return facts


@router.get("/hechos/movimientos", response_model=List[BIMovimientoFact])
async def obtener_hechos_movimientos(
    fecha_desde: Optional[datetime] = Query(None, description="Filtro fecha inicio ISO"),
    fecha_hasta: Optional[datetime] = Query(None, description="Filtro fecha fin ISO"),
    limit: int = Query(5000, ge=1, le=20000),
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Retorna la tabla de hechos de transacciones de movimientos.
    NUNCA expone el RUT del operario (cumple Ley 19.628); utiliza código de empleado.
    """
    stmt = (
        select(
            MovimientoV2,
            TipoMovimiento.codigo.label("tipo_codigo"),
            Item.codigo.label("item_codigo"),
            Lote.numero_lote,
            Usuario.codigo_empleado,
        )
        .join(TipoMovimiento, MovimientoV2.id_tipo_movimiento == TipoMovimiento.id)
        .join(Item, MovimientoV2.id_item == Item.id)
        .outerjoin(Lote, MovimientoV2.id_lote == Lote.id)
        .join(Usuario, MovimientoV2.id_usuario == Usuario.id)
        .where(MovimientoV2.id_organizacion == tenant.id_organizacion)
    )
    stmt = scope_movement_query(stmt, tenant, MovimientoV2)
    if fecha_desde:
        stmt = stmt.where(MovimientoV2.fecha_hora >= fecha_desde)
    if fecha_hasta:
        stmt = stmt.where(MovimientoV2.fecha_hora <= fecha_hasta)

    stmt = stmt.order_by(MovimientoV2.fecha_hora.asc()).limit(limit)
    res = await db.execute(stmt)

    movs = []
    for mov, tipo_cod, it_cod, num_lot, emp_cod in res.all():
        movs.append(
            BIMovimientoFact(
                id_movimiento=mov.id,
                fecha_hora=mov.fecha_hora,
                id_tipo_movimiento=mov.id_tipo_movimiento,
                tipo_movimiento_codigo=tipo_cod,
                efecto_stock=mov.efecto_stock,
                codigo_item=it_cod,
                numero_lote=num_lot,
                codigo_ubicacion_origen=mov.id_ubicacion_origen,
                codigo_ubicacion_destino=mov.id_ubicacion_destino,
                cantidad=mov.cantidad,
                unidad_medida=mov.unidad_medida,
                codigo_empleado_operario=emp_cod or "EXTERNO",
            )
        )
    return movs


@router.get("/hechos/inconsistencias", response_model=List[BIInconsistenciaFact])
async def obtener_hechos_inconsistencias(
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Retorna el historial de inconsistencias de importación para análisis de calidad de inventario."""
    inconsistencias = await ModuleRegistry.collect_report(
        db, tenant, "inconsistencias_bi", limit=5000,
    )
    return [
        BIInconsistenciaFact(
            id_inconsistencia=inc.id,
            id_ubicacion=inc.id_ubicacion,
            fecha_deteccion=inc.fecha_deteccion,
            tipo_inconsistencia=inc.tipo_inconsistencia,
            codigo_ubicacion=inc.codigo_ubicacion,
            codigo_item=inc.codigo_item,
            numero_lote=inc.numero_lote,
            cantidad_externa=inc.cantidad_externa,
            resuelto=inc.resuelto,
        )
        for inc in inconsistencias[:5000]
    ]
