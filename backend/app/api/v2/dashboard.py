from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies_v2 import TenantContext, get_current_tenant, require_permission
from app.core.modules.registry import ModuleRegistry
from app.core.site_access import allowed_location_ids, scope_alert_query, scope_movement_query
from app.database import get_db
from app.models.v2.alerta import AlertaV2
from app.models.v2.item import Item
from app.models.v2.lote import Lote
from app.models.v2.movimiento import MovimientoV2
from app.models.v2.saldo_stock import SaldoStock
from app.models.v2.ubicacion import Ubicacion
from app.schemas.v2.dashboard import (
    DashboardKPIs,
    InconsistenciaDashboardItem,
    UbicacionOcupacionItem,
)
from app.services.v2.export_service import ExportServiceV2
from app.services.v2.configuracion_operativa import obtener_configuracion

router = APIRouter(prefix="/dashboard", tags=["V2 - Dashboard y Reportes"],
                   dependencies=[Depends(require_permission("dashboard:read"))])


# ─── Indicadores KPIs de Supervisor ──────────────────────────────────────────

@router.get("/kpis", response_model=DashboardKPIs)
async def obtener_kpis_supervisor(
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Retorna los 5 indicadores mínimos requeridos para supervisor (Fase 1F):
    1. Capacidad instalada total
    2. Stock total acumulado
    3. Ubicaciones libres
    4. Porcentaje de uso global
    5. Cantidad de inconsistencias detectadas
    """
    org_id = tenant.id_organizacion

    # 1. Ubicaciones: capacidad y ocupación
    stmt_ubis = select(
        func.coalesce(func.sum(Ubicacion.capacidad_maxima), 0).label("capacidad_instalada"),
        func.coalesce(func.sum(Ubicacion.ocupacion_actual), 0).label("ocupacion_total"),
        func.count(Ubicacion.id).label("total_ubis"),
        func.count(Ubicacion.id).filter(Ubicacion.ocupacion_actual == 0).label("ubis_libres"),
    ).where(Ubicacion.id_organizacion == org_id, Ubicacion.activo == True)
    if tenant.sitios_permitidos is not None:
        stmt_ubis = stmt_ubis.where(Ubicacion.id.in_(allowed_location_ids(tenant)))
    res_ubis = (await db.execute(stmt_ubis)).one()

    cap_instalada = Decimal(str(res_ubis.capacidad_instalada))
    ocup_total = Decimal(str(res_ubis.ocupacion_total))
    total_ubis = res_ubis.total_ubis
    ubis_libres = res_ubis.ubis_libres

    pct_uso = float((ocup_total / cap_instalada * 100)) if cap_instalada > 0 else 0.0
    stmt_por_unidad = select(
        Ubicacion.unidad_capacidad,
        func.sum(Ubicacion.capacidad_maxima),
        func.sum(Ubicacion.ocupacion_actual),
    ).where(Ubicacion.id_organizacion == org_id, Ubicacion.activo.is_(True))
    if tenant.sitios_permitidos is not None:
        stmt_por_unidad = stmt_por_unidad.where(Ubicacion.id.in_(allowed_location_ids(tenant)))
    stmt_por_unidad = stmt_por_unidad.group_by(Ubicacion.unidad_capacidad)
    capacidad_por_unidad = {}
    ocupacion_por_unidad = {}
    porcentaje_por_unidad = {}
    for unidad, capacidad, ocupacion in (await db.execute(stmt_por_unidad)).all():
        capacidad_por_unidad[unidad] = Decimal(str(capacidad))
        ocupacion_por_unidad[unidad] = Decimal(str(ocupacion))
        porcentaje_por_unidad[unidad] = round(float(ocupacion / capacidad * 100), 2) if capacidad else 0.0

    # 2. Stock total consolidado
    stmt_stock = select(func.coalesce(func.sum(SaldoStock.cantidad), 0)).where(
        SaldoStock.id_organizacion == org_id
    )
    if tenant.sitios_permitidos is not None:
        stmt_stock = stmt_stock.where(SaldoStock.id_ubicacion.in_(allowed_location_ids(tenant)))
    stock_total = Decimal(str((await db.execute(stmt_stock)).scalar_one()))
    stmt_stock_unidad = select(SaldoStock.unidad_medida, func.sum(SaldoStock.cantidad)).where(
        SaldoStock.id_organizacion == org_id,
    )
    if tenant.sitios_permitidos is not None:
        stmt_stock_unidad = stmt_stock_unidad.where(SaldoStock.id_ubicacion.in_(allowed_location_ids(tenant)))
    stock_por_unidad = {unidad: Decimal(str(cantidad)) for unidad, cantidad in (
        await db.execute(stmt_stock_unidad.group_by(SaldoStock.unidad_medida))
    ).all()}

    # 3. Cantidad de inconsistencias no resueltas
    cant_inconsistencias = await ModuleRegistry.collect_report(db, tenant, "inconsistencias_count")

    # 4. Total ítems y alertas activas
    stmt_items = select(func.count(Item.id)).where(Item.id_organizacion == org_id, Item.activo == True)
    total_items = (await db.execute(stmt_items)).scalar_one()

    stmt_alertas = select(func.count(AlertaV2.id)).where(
        AlertaV2.id_organizacion == org_id,
        AlertaV2.estado == "activa",
    )
    stmt_alertas = scope_alert_query(stmt_alertas, tenant, AlertaV2)
    cant_alertas = (await db.execute(stmt_alertas)).scalar_one()

    return DashboardKPIs(
        capacidad_instalada=cap_instalada,
        stock_total=stock_total,
        ubicaciones_libres=ubis_libres,
        porcentaje_uso=round(pct_uso, 2),
        cantidad_inconsistencias=cant_inconsistencias,
        total_ubicaciones=total_ubis,
        total_items=total_items,
        alertas_activas=cant_alertas,
        capacidad_por_unidad=capacidad_por_unidad,
        ocupacion_por_unidad=ocupacion_por_unidad,
        porcentaje_por_unidad=porcentaje_por_unidad,
        stock_por_unidad=stock_por_unidad,
        totales_comparables=len(capacidad_por_unidad) <= 1 and len(stock_por_unidad) <= 1,
    )


@router.get("/ocupacion", response_model=List[UbicacionOcupacionItem])
async def listar_ocupacion_ubicaciones(
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Retorna el listado de ubicaciones con su porcentaje de ocupación actual."""
    stmt = (
        select(Ubicacion)
        .where(Ubicacion.id_organizacion == tenant.id_organizacion, Ubicacion.activo == True)
        .order_by(Ubicacion.codigo.asc())
    )
    if tenant.sitios_permitidos is not None:
        stmt = stmt.where(Ubicacion.id.in_(allowed_location_ids(tenant)))
    ubis = (await db.execute(stmt)).scalars().all()
    umbrales = (await obtener_configuracion(db, tenant.id_organizacion)).umbrales_color
    resultado = []
    for u in ubis:
        pct = float((u.ocupacion_actual / u.capacidad_maxima * 100)) if u.capacidad_maxima > 0 else 0.0
        resultado.append(
            UbicacionOcupacionItem(
                id_ubicacion=u.id,
                codigo=u.codigo,
                capacidad_maxima=u.capacidad_maxima,
                ocupacion_actual=u.ocupacion_actual,
                porcentaje_ocupacion=round(pct, 2),
                unidad_capacidad=u.unidad_capacidad,
                estado="critica" if pct >= umbrales.critica else ("alerta" if pct >= umbrales.alerta else "optima"),
            )
        )
    return resultado


@router.get("/inconsistencias-recientes", response_model=List[InconsistenciaDashboardItem])
async def consultar_inconsistencias_recientes(
    limit: int = Query(10, ge=1, le=50),
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Retorna inconsistencias recientes con referencia de ubicación
    para que el supervisor pueda navegar directamente hacia ella.
    """
    inconsistencias = await ModuleRegistry.collect_report(
        db, tenant, "inconsistencias_recientes", limit=limit,
    )
    items = []
    for inc in inconsistencias[:limit]:
        items.append(
            InconsistenciaDashboardItem(
                id=inc.id,
                id_ubicacion=inc.id_ubicacion,
                id_job=inc.id_importacion_job,
                fila_origen=inc.fila_origen,
                tipo_inconsistencia=inc.tipo_inconsistencia,
                motivo=inc.motivo,
                codigo_ubicacion=inc.codigo_ubicacion,
                codigo_item=inc.codigo_item,
                numero_lote=inc.numero_lote,
                cantidad_externa=inc.cantidad_externa,
                fecha_deteccion=inc.fecha_deteccion.isoformat(),
            )
        )
    return items


# ─── Servicios Reutilizables de Exportación (CSV, Excel, PDF) ─────────────────

async def _obtener_datos_movimientos_export(db: AsyncSession, tenant: TenantContext) -> tuple[List[str], List[List[str]]]:
    cabeceras = ["ID Movimiento", "Fecha y Hora", "Tipo", "Efecto", "Ítem", "Lote", "Origen", "Destino", "Cantidad", "Unidad"]
    stmt = (
        select(MovimientoV2, Item.codigo, Lote.numero_lote)
        .join(Item, MovimientoV2.id_item == Item.id)
        .outerjoin(Lote, MovimientoV2.id_lote == Lote.id)
        .where(MovimientoV2.id_organizacion == tenant.id_organizacion)
        .order_by(MovimientoV2.fecha_hora.desc())
    )
    stmt = scope_movement_query(stmt, tenant, MovimientoV2)
    res = await db.execute(stmt)
    filas = []
    for mov, cod_item, num_lote in res.all():
        filas.append([
            mov.id[:8],
            mov.fecha_hora.strftime("%Y-%m-%d %H:%M"),
            mov.id_tipo_movimiento[:8],
            mov.efecto_stock,
            cod_item,
            num_lote or "-",
            mov.id_ubicacion_origen[:8] if mov.id_ubicacion_origen else "-",
            mov.id_ubicacion_destino[:8] if mov.id_ubicacion_destino else "-",
            str(mov.cantidad),
            mov.unidad_medida,
        ])
    return cabeceras, filas


@router.get("/exportar/movimientos/csv")
async def exportar_movimientos_csv(
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Exporta el historial de movimientos de la organización en formato CSV."""
    cabeceras, filas = await _obtener_datos_movimientos_export(db, tenant)
    csv_bytes = ExportServiceV2.exportar_csv(cabeceras, filas)
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=movimientos_{tenant.id_organizacion[:8]}.csv"},
    )


@router.get("/exportar/movimientos/excel")
async def exportar_movimientos_excel(
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Exporta el historial de movimientos de la organización en archivo Excel (.xlsx)."""
    cabeceras, filas = await _obtener_datos_movimientos_export(db, tenant)
    excel_bytes = ExportServiceV2.exportar_excel("Movimientos", cabeceras, filas)
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=movimientos_{tenant.id_organizacion[:8]}.xlsx"},
    )


@router.get("/exportar/movimientos/pdf")
async def exportar_movimientos_pdf(
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Exporta reporte formal en PDF de movimientos (Ley 19.628: sin datos personales ni RUT)."""
    cabeceras, filas = await _obtener_datos_movimientos_export(db, tenant)
    pdf_bytes = ExportServiceV2.exportar_pdf(
        titulo="Reporte Oficial de Movimientos de Inventario",
        subtitulo=f"Organización ID: {tenant.id_organizacion} — Generado: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC",
        cabeceras=cabeceras,
        filas=filas,
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=reporte_movimientos_{tenant.id_organizacion[:8]}.pdf"},
    )
