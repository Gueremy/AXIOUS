"""
app/api/reportes.py
Endpoints de exportación — Sprint 4 (AXI-19).

Endpoints:
  GET /reportes/movimientos/pdf    → archivo PDF descargable
  GET /reportes/movimientos/excel  → archivo Excel .xlsx descargable
  GET /reportes/sernapesca         → Excel formato SERNAPESCA

⚠️ NUNCA incluir RUT en ningún reporte (Ley 19.628)
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
import io

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.container import Container
from app.models.galpon import Galpon
from app.models.movimiento import Movimiento
from app.models.usuario import Usuario
from app.services.reportes import (
    generar_pdf_movimientos,
    generar_excel_movimientos,
    generar_reporte_sernapesca,
)
from app.core.dependencies import require_role

router = APIRouter()

ROLES_REPORTE = ["jefe_bodega", "admin_sede", "super_admin"]
ROLES_SERNAPESCA = ["admin_sede", "super_admin"]


def _resolver_sede(current_user: Usuario, id_sede_param: Optional[str] = None) -> Optional[str]:
    if current_user.rol == "super_admin" and id_sede_param:
        return id_sede_param
    return current_user.id_sede


async def _obtener_movimientos_para_reporte(
    db: AsyncSession,
    sede_id: str,
    desde: datetime,
    hasta: datetime,
    tipo: Optional[str] = None,
) -> list[dict]:
    """Consulta los movimientos aprobados del período y retorna lista de dicts."""
    stmt = (
        select(
            Movimiento,
            Container.codigo.label("container_codigo"),
            Container.unidad_medida.label("unidad_medida"),
            Galpon.nombre.label("galpon_nombre"),
            Usuario.codigo_empleado.label("codigo_empleado"),
            # NUNCA rut (Ley 19.628)
        )
        .join(Container, Movimiento.id_container == Container.id)
        .join(Galpon, Container.id_galpon == Galpon.id)
        .join(Usuario, Movimiento.id_usuario == Usuario.id)
        .where(
            Galpon.id_sede == sede_id,
            Movimiento.estado == "aprobado",
            Movimiento.fecha_hora >= desde,
            Movimiento.fecha_hora < hasta,
        )
    )
    if tipo:
        stmt = stmt.where(Movimiento.tipo == tipo)
    stmt = stmt.order_by(Movimiento.fecha_hora.desc())

    rows = (await db.execute(stmt)).all()
    result = []
    for row in rows:
        mov = row[0]
        result.append({
            "fecha_hora": mov.fecha_hora,
            "tipo": mov.tipo,
            "estado": mov.estado,
            "numero_lote": mov.numero_lote,
            "cantidad": float(mov.cantidad),
            "unidad_medida": row.unidad_medida,
            "nombre_proveedor": mov.nombre_proveedor,
            "num_guia_despacho": mov.num_guia_despacho,
            "registro_sanitario": mov.registro_sanitario,
            "fecha_fabricacion": mov.fecha_fabricacion,
            "fecha_vencimiento": mov.fecha_vencimiento,
            "temperatura_almacen": float(mov.temperatura_almacen) if mov.temperatura_almacen is not None else None,
            "num_receta_retenida": mov.num_receta_retenida,
            "num_autorizacion_sag": mov.num_autorizacion_sag,
            "container_codigo": row.container_codigo,
            "galpon_nombre": row.galpon_nombre,
            "codigo_empleado": row.codigo_empleado,
            # NUNCA rut (Ley 19.628)
        })
    return result


# ── GET /reportes/movimientos/pdf ─────────────────────────────────────────────

@router.get("/movimientos/pdf")
async def exportar_pdf(
    dias: int = Query(30, ge=1, le=365, description="Días hacia atrás"),
    desde: Optional[str] = Query(None, description="ISO date YYYY-MM-DD"),
    hasta: Optional[str] = Query(None, description="ISO date YYYY-MM-DD"),
    tipo: Optional[str] = Query(None),
    id_sede: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role(ROLES_REPORTE)),
) -> Any:
    """Descarga un PDF con movimientos SERNAPESCA del período."""
    sede_id = _resolver_sede(current_user, id_sede)
    ahora = datetime.now(timezone.utc)
    fecha_hasta = datetime.fromisoformat(hasta).replace(tzinfo=timezone.utc) + timedelta(days=1) if hasta else ahora
    fecha_desde = datetime.fromisoformat(desde).replace(tzinfo=timezone.utc) if desde else ahora - timedelta(days=dias)

    movimientos = await _obtener_movimientos_para_reporte(db, sede_id, fecha_desde, fecha_hasta, tipo)

    pdf_bytes = generar_pdf_movimientos(
        movimientos,
        nombre_sede=sede_id,
        desde=fecha_desde,
        hasta=fecha_hasta,
    )

    nombre_archivo = f"movimientos_skretting_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
    )


# ── GET /reportes/movimientos/excel ──────────────────────────────────────────

@router.get("/movimientos/excel")
async def exportar_excel(
    dias: int = Query(30, ge=1, le=365),
    desde: Optional[str] = Query(None),
    hasta: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    id_sede: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role(ROLES_REPORTE)),
) -> Any:
    """Descarga un Excel .xlsx con movimientos auditables."""
    sede_id = _resolver_sede(current_user, id_sede)
    ahora = datetime.now(timezone.utc)
    fecha_hasta = datetime.fromisoformat(hasta).replace(tzinfo=timezone.utc) + timedelta(days=1) if hasta else ahora
    fecha_desde = datetime.fromisoformat(desde).replace(tzinfo=timezone.utc) if desde else ahora - timedelta(days=dias)

    movimientos = await _obtener_movimientos_para_reporte(db, sede_id, fecha_desde, fecha_hasta, tipo)

    excel_bytes = generar_excel_movimientos(movimientos, nombre_sede=sede_id)

    nombre_archivo = f"movimientos_skretting_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
    )


# ── GET /reportes/sernapesca ──────────────────────────────────────────────────

@router.get("/sernapesca")
async def exportar_sernapesca(
    dias: int = Query(30, ge=1, le=365),
    desde: Optional[str] = Query(None),
    hasta: Optional[str] = Query(None),
    id_sede: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role(ROLES_SERNAPESCA)),
) -> Any:
    """Descarga Excel con formato oficial SERNAPESCA (sin RUT — Ley 19.628)."""
    sede_id = _resolver_sede(current_user, id_sede)
    ahora = datetime.now(timezone.utc)
    fecha_hasta = datetime.fromisoformat(hasta).replace(tzinfo=timezone.utc) + timedelta(days=1) if hasta else ahora
    fecha_desde = datetime.fromisoformat(desde).replace(tzinfo=timezone.utc) if desde else ahora - timedelta(days=dias)

    # SERNAPESCA solo incluye entradas_proveedor (no traslados internos)
    movimientos = await _obtener_movimientos_para_reporte(
        db, sede_id, fecha_desde, fecha_hasta, tipo="entrada_proveedor"
    )

    excel_bytes = generar_reporte_sernapesca(movimientos, nombre_sede=sede_id)

    nombre_archivo = f"sernapesca_skretting_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
    )
