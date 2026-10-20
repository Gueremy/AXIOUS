"""Exportación paginada de los conjuntos de datos visibles en la API v2."""
import json
import os
import tempfile
import zipfile
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.background import BackgroundTask

from app.core.dependencies_v2 import TenantContext, get_current_tenant, require_permission
from app.core.modules.registry import ModuleRegistry
from app.core.site_access import allowed_location_ids, scope_alert_query, scope_movement_query
from app.database import get_db
from app.models.v2.alerta import AlertaV2, ReglaAlertaV2
from app.models.v2.esquema_atributos import EsquemaAtributos
from app.models.v2.item import Item
from app.models.v2.lote import Lote
from app.models.v2.movimiento import MovimientoV2
from app.models.v2.regla_ubicacion import ReglaUbicacion
from app.models.v2.saldo_stock import SaldoStock
from app.models.v2.sitio import Sitio
from app.models.v2.solicitud_movimiento import SolicitudMovimiento
from app.models.v2.tipo_movimiento import TipoMovimiento
from app.models.v2.ubicacion import Ubicacion
from app.models.v2.zona import Zona
from app.services.v2.export_service import ExportServiceV2
from app.api.v2.dashboard import obtener_kpis_supervisor, listar_ocupacion_ubicaciones
from app.api.v2.bi import (
    obtener_dimension_sitios, obtener_dimension_items, obtener_hechos_stock,
    obtener_hechos_movimientos, obtener_hechos_inconsistencias,
)

router = APIRouter(prefix="/exportaciones", tags=["V2 - Exportaciones"],
                   dependencies=[Depends(require_permission("reporte:export"))])

RECURSOS = {
    "sitios": (Sitio, ("codigo", "nombre", "tipo", "descripcion", "ubicacion_geografica", "atributos", "activo")),
    "zonas": (Zona, ("codigo", "nombre", "tipo", "id_sitio", "id_zona_padre", "layout", "atributos", "activo")),
    "ubicaciones": (Ubicacion, ("codigo", "id_zona", "capacidad_maxima", "unidad_capacidad", "ocupacion_actual", "estado", "layout", "atributos", "activo")),
    "items": (Item, ("codigo", "nombre", "categoria", "unidad_medida", "atributos", "activo")),
    "lotes": (Lote, ("numero_lote", "id_item", "fecha_fabricacion", "fecha_vencimiento", "atributos", "estado")),
    "stock": (SaldoStock, ("id_ubicacion", "id_item", "id_lote", "cantidad", "unidad_medida")),
    "tipos-movimiento": (TipoMovimiento, ("codigo", "nombre", "efecto_stock", "requiere_aprobacion", "activo")),
    "solicitudes": (SolicitudMovimiento, ("id", "id_tipo_movimiento", "id_item", "id_ubicacion_origen", "id_ubicacion_destino", "cantidad", "unidad_medida", "estado", "fecha_creacion")),
    "movimientos": (MovimientoV2, ("id", "id_tipo_movimiento", "id_item", "id_ubicacion_origen", "id_ubicacion_destino", "cantidad", "unidad_medida", "fecha_hora")),
    "reglas": (ReglaUbicacion, ("codigo", "nombre", "tipo_regla", "id_sitio", "id_zona", "id_ubicacion", "configuracion", "activo")),
    "alertas": (AlertaV2, ("tipo", "severidad", "titulo", "descripcion", "id_ubicacion", "estado", "fecha_generacion")),
    "reglas-alerta": (ReglaAlertaV2, ("codigo", "nombre", "tipo", "configuracion", "severidad", "habilitada")),
    "esquemas": (EsquemaAtributos, ("entidad", "nombre", "version", "schema_json", "activo")),
    "importaciones": (None, ("nombre_archivo", "tipo_fuente", "estado", "total_registros", "registros_inconsistentes", "fecha_inicio")),
    "inconsistencias": (None, ("fila_origen", "tipo_inconsistencia", "motivo", "codigo_ubicacion", "codigo_item", "cantidad_externa", "resuelto", "fecha_deteccion")),
}

DYNAMIC_RECURSOS = {
    "kpis": obtener_kpis_supervisor,
    "ocupacion": listar_ocupacion_ubicaciones,
    "bi-sitios": obtener_dimension_sitios,
    "bi-items": obtener_dimension_items,
    "bi-stock": obtener_hechos_stock,
    "bi-movimientos": obtener_hechos_movimientos,
    "bi-inconsistencias": obtener_hechos_inconsistencias,
}


def _alcance(stmt, tenant: TenantContext, modelo):
    if modelo in (MovimientoV2, SolicitudMovimiento):
        return scope_movement_query(stmt, tenant, modelo)
    if modelo is AlertaV2:
        return scope_alert_query(stmt, tenant, modelo)
    if tenant.sitios_permitidos is None:
        return stmt
    if modelo is Sitio:
        return stmt.where(Sitio.id.in_(tenant.sitios_permitidos))
    if modelo is Zona:
        return stmt.where(Zona.id_sitio.in_(tenant.sitios_permitidos))
    if modelo is Ubicacion:
        return stmt.where(Ubicacion.id.in_(allowed_location_ids(tenant)))
    if modelo is SaldoStock:
        return stmt.where(SaldoStock.id_ubicacion.in_(allowed_location_ids(tenant)))
    if modelo is ReglaUbicacion:
        from app.api.v2.reglas import _scope_reglas
        return _scope_reglas(stmt, tenant)
    return stmt


def _celda(valor):
    if valor is None:
        return ""
    if isinstance(valor, (dict, list)):
        return json.dumps(valor, ensure_ascii=False, default=str)
    if isinstance(valor, datetime):
        return valor.isoformat()
    return str(valor)


@router.get("/{recurso}/{formato}")
async def exportar_recurso(
    recurso: str,
    formato: Literal["csv", "excel", "pdf"],
    page: int = Query(1, ge=1),
    size: int = Query(1000, ge=1, le=10000),
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    spec = RECURSOS.get(recurso)
    if spec is None and recurso not in DYNAMIC_RECURSOS:
        raise HTTPException(status_code=404, detail="Recurso exportable no encontrado")
    if recurso in DYNAMIC_RECURSOS:
        funcion = DYNAMIC_RECURSOS[recurso]
        if recurso == "bi-movimientos":
            datos = await funcion(fecha_desde=None, fecha_hasta=None, limit=20000,
                                  tenant=tenant, db=db)
        else:
            datos = await funcion(tenant=tenant, db=db)
        objetos = datos if isinstance(datos, list) else [datos]
        total = len(objetos)
        cabeceras = list(objetos[0].model_dump().keys()) if objetos else ["sin_datos"]
        objetos = objetos[(page - 1) * size:page * size]
        filas = [[_celda(obj.model_dump().get(campo)) for campo in cabeceras] for obj in objetos]
    else:
        modelo, campos = spec
        if modelo is None:
            resultado = await ModuleRegistry.collect_report(
                db, tenant, f"export_{recurso}", offset=(page - 1) * size, limit=size,
            )
            if resultado is None:
                raise HTTPException(status_code=403, detail="Módulo de importación deshabilitado")
            objetos, total = resultado
        else:
            stmt = _alcance(select(modelo).where(modelo.id_organizacion == tenant.id_organizacion),
                            tenant, modelo)
            total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
            objetos = (await db.execute(stmt.order_by(modelo.id).offset((page - 1) * size).limit(size))).scalars().all()
        filas = [[_celda(getattr(obj, campo)) for campo in campos] for obj in objetos]
        cabeceras = list(campos)
    nombre = f"{recurso}_{tenant.id_organizacion[:8]}_p{page}"
    headers = {"X-Export-Total": str(total), "X-Export-Page": str(page)}
    if formato == "csv":
        contenido = ExportServiceV2.exportar_csv(cabeceras, filas)
        mime, extension = "text/csv", "csv"
    elif formato == "excel":
        contenido = ExportServiceV2.exportar_excel(recurso, cabeceras, filas)
        mime, extension = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"
    else:
        contenido = ExportServiceV2.exportar_pdf(
            titulo=f"Reporte de {recurso}",
            subtitulo=f"Organización {tenant.id_organizacion} · {datetime.now(timezone.utc).isoformat()}",
            cabeceras=cabeceras, filas=filas,
        )
        mime, extension = "application/pdf", "pdf"
    headers["Content-Disposition"] = f"attachment; filename={nombre}.{extension}"
    return Response(content=contenido, media_type=mime, headers=headers)


@router.get("/{recurso}/{formato}/completo")
async def exportar_recurso_completo(
    recurso: str,
    formato: Literal["csv", "excel", "pdf"],
    size: int = Query(10000, ge=1, le=10000),
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Crea un ZIP paginado desde una sola instantánea de PostgreSQL.

    El archivo se materializa en disco antes de responder. Así se cierra la
    transacción y se libera su conexión incluso si el cliente descarga lento.
    """
    extension = {"csv": "csv", "excel": "xlsx", "pdf": "pdf"}[formato]
    fd, path = tempfile.mkstemp(prefix="salmo-export-", suffix=".zip")
    os.close(fd)
    try:
        session_factory = async_sessionmaker(bind=db.bind, expire_on_commit=False)
        async with session_factory() as export_db:
            if export_db.bind.dialect.name == "postgresql":
                await export_db.connection(execution_options={"isolation_level": "REPEATABLE READ"})
                await export_db.execute(text("SET TRANSACTION READ ONLY"))
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
                page = 1
                total = None
                while True:
                    response = await exportar_recurso(
                        recurso, formato, page=page, size=size, tenant=tenant, db=export_db,
                    )
                    page_total = int(response.headers["X-Export-Total"])
                    if total is None:
                        total = page_total
                    elif page_total != total:
                        raise HTTPException(status_code=409, detail="Los datos cambiaron durante la exportación")
                    archive.writestr(f"pagina-{page:03d}.{extension}", response.body)
                    if page * size >= total:
                        break
                    page += 1
                archive.writestr("manifest.json", json.dumps({
                    "recurso": recurso, "formato": formato,
                    "total": total, "paginas": page,
                    "fecha_generacion": datetime.now(timezone.utc).isoformat(),
                }, ensure_ascii=False))
        return FileResponse(
            path, media_type="application/zip",
            filename=f"{recurso}_{tenant.id_organizacion[:8]}_completo.zip",
            background=BackgroundTask(os.unlink, path),
            headers={"X-Export-Total": str(total), "X-Export-Pages": str(page)},
        )
    except BaseException:
        os.unlink(path)
        raise
