"""
app/api/dashboard.py
Dashboard KPIs — Sprint 4 (AXI-18).

Endpoints:
  GET /dashboard/kpis                  — 4 KPIs globales de la sede
  GET /dashboard/ocupacion-por-galpon  — ocupación % por galpón (Recharts BarChart)
  GET /dashboard/evolucion             — movimientos por día (Recharts LineChart)

Reglas:
  - Filtrar SIEMPRE por id_sede del token (aislamiento multi-sede)
  - super_admin puede pasar ?id_sede=X para ver cualquier sede
  - NUNCA exponer RUT (Ley 19.628)
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, case, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.alerta import Alerta
from app.models.container import Container
from app.models.galpon import Galpon
from app.models.movimiento import Movimiento
from app.models.usuario import Usuario
from app.schemas.dashboard import KPIResponse, OcupacionGalponItem, EvolucionItem
from app.core.dependencies import require_role

router = APIRouter()

ROLES_DASHBOARD = ["jefe_bodega", "admin_sede", "super_admin", "gerencia"]


def _resolver_sede(current_user: Usuario, id_sede_param: Optional[str] = None) -> Optional[str]:
    """
    Retorna el id_sede efectivo para los queries.
    - super_admin puede pasar ?id_sede=X para ver cualquier sede.
    - El resto usa siempre su propia sede.
    """
    if current_user.rol == "super_admin" and id_sede_param:
        return id_sede_param
    return current_user.id_sede


# ── GET /dashboard/kpis ───────────────────────────────────────────────────────

@router.get("/kpis", response_model=KPIResponse)
async def get_kpis(
    id_sede: Optional[str] = Query(None, description="Solo para super_admin"),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role(ROLES_DASHBOARD)),
) -> Any:
    """Retorna los 4 KPIs globales de la sede."""
    sede_id = _resolver_sede(current_user, id_sede)

    # BUG-2 FIX: si el usuario no tiene sede, fallar claro en vez de retornar 0s sin sentido
    if not sede_id:
        raise HTTPException(status_code=400, detail="El usuario no tiene sede asignada. Contactar a super_admin.")

    # 1. Ocupación global (sum ocupacion_actual / sum capacidad_max * 100)
    ocup_stmt = (
        select(
            func.coalesce(func.sum(Container.ocupacion_actual), 0).label("total_ocup"),
            func.coalesce(func.sum(Container.capacidad_max), 0).label("total_cap"),
        )
        .join(Galpon, Container.id_galpon == Galpon.id)
        .where(Galpon.id_sede == sede_id)
    )
    ocup_row = (await db.execute(ocup_stmt)).first()
    if ocup_row and ocup_row.total_cap and float(ocup_row.total_cap) > 0:
        ocupacion_global = round(float(ocup_row.total_ocup) / float(ocup_row.total_cap) * 100, 1)
    else:
        ocupacion_global = 0.0

    # 2. Alertas activas de la sede
    alertas_activas = await db.scalar(
        select(func.count())
        .select_from(Alerta)
        .join(Container, Alerta.id_container == Container.id)
        .join(Galpon, Container.id_galpon == Galpon.id)
        .where(Galpon.id_sede == sede_id, Alerta.estado == "activa")
    ) or 0

    # 3. Movimientos de hoy (usando UTC, que corresponde al día en Chile con offset -4)
    hoy_inicio = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    hoy_fin = hoy_inicio + timedelta(days=1)

    movimientos_hoy = await db.scalar(
        select(func.count())
        .select_from(Movimiento)
        .join(Container, Movimiento.id_container == Container.id)
        .join(Galpon, Container.id_galpon == Galpon.id)
        .where(
            Galpon.id_sede == sede_id,
            Movimiento.fecha_hora >= hoy_inicio,
            Movimiento.fecha_hora < hoy_fin,
        )
    ) or 0

    # 4. Próximo vencimiento (días mínimos al vencimiento entre todos los lotes activos)
    ahora = datetime.now(timezone.utc)
    proximo_stmt = (
        select(func.min(Movimiento.fecha_vencimiento))
        .join(Container, Movimiento.id_container == Container.id)
        .join(Galpon, Container.id_galpon == Galpon.id)
        .where(
            Galpon.id_sede == sede_id,
            Movimiento.estado == "aprobado",
            Movimiento.fecha_vencimiento.isnot(None),
            Movimiento.fecha_vencimiento > ahora,
        )
    )
    proximo = (await db.execute(proximo_stmt)).scalar()
    proximo_dias = None
    if proximo:
        # Asegurarse que proximo tenga timezone para comparar con ahora (timezone-aware)
        if proximo.tzinfo is None:
            from datetime import timezone as tz
            proximo = proximo.replace(tzinfo=tz.utc)
        proximo_dias = (proximo - ahora).days

    return KPIResponse(
        ocupacion_global=ocupacion_global,
        alertas_activas=int(alertas_activas),
        movimientos_hoy=int(movimientos_hoy),
        proximo_vencimiento=proximo_dias,
    )


# ── GET /dashboard/ocupacion-por-galpon ──────────────────────────────────────

@router.get("/ocupacion-por-galpon", response_model=list[OcupacionGalponItem])
async def get_ocupacion_por_galpon(
    id_sede: Optional[str] = Query(None, description="Solo para super_admin"),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role(ROLES_DASHBOARD)),
) -> Any:
    """Retorna la ocupación % por galpón para un BarChart de Recharts."""
    sede_id = _resolver_sede(current_user, id_sede)

    stmt = (
        select(
            Galpon.nombre.label("nombre"),
            func.coalesce(func.sum(Container.ocupacion_actual), 0).label("total_ocup"),
            func.coalesce(func.sum(Container.capacidad_max), 0).label("total_cap"),
        )
        .join(Container, Container.id_galpon == Galpon.id)
        .where(Galpon.id_sede == sede_id)
        .group_by(Galpon.id, Galpon.nombre)
        .order_by(Galpon.nombre)
    )
    rows = (await db.execute(stmt)).all()

    resultado = []
    for row in rows:
        if row.total_cap and float(row.total_cap) > 0:
            pct = round(float(row.total_ocup) / float(row.total_cap) * 100, 1)
        else:
            pct = 0.0

        if pct > 80:
            estado = "critico"
        elif pct > 50:
            estado = "medio"
        else:
            estado = "disponible"

        resultado.append(OcupacionGalponItem(
            name=row.nombre,
            ocupacion_pct=pct,
            ocup=pct,          # BUG-3 FIX: alias requerido por el frontend
            estado=estado,
        ))

    return resultado


# ── GET /dashboard/evolucion ──────────────────────────────────────────────────

@router.get("/evolucion", response_model=list[EvolucionItem])
async def get_evolucion(
    dias: int = Query(30, ge=1, le=90, description="Días hacia atrás (máx 90)"),
    id_sede: Optional[str] = Query(None, description="Solo para super_admin"),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role(ROLES_DASHBOARD)),
) -> Any:
    """Retorna la evolución de movimientos aprobados por día para un LineChart de Recharts."""
    sede_id = _resolver_sede(current_user, id_sede)
    ahora = datetime.now(timezone.utc)
    desde = ahora - timedelta(days=dias)

    # SQLite: usar strftime; PostgreSQL: usar DATE(). Usamos func.date() que funciona en ambos
    stmt = (
        select(
            func.date(Movimiento.fecha_hora).label("fecha"),
            func.count().label("movimientos"),
            func.sum(
                case((Movimiento.tipo == "entrada_proveedor", 1), else_=0)
            ).label("entradas"),
            func.sum(
                case((Movimiento.tipo == "salida_produccion", 1), else_=0)
            ).label("salidas"),
        )
        .join(Container, Movimiento.id_container == Container.id)
        .join(Galpon, Container.id_galpon == Galpon.id)
        .where(
            Galpon.id_sede == sede_id,
            Movimiento.estado == "aprobado",
            Movimiento.fecha_hora >= desde,
        )
        .group_by(func.date(Movimiento.fecha_hora))
        .order_by(func.date(Movimiento.fecha_hora).asc())
    )
    rows = (await db.execute(stmt)).all()

    return [
        EvolucionItem(
            fecha=str(row.fecha),
            movimientos=int(row.movimientos),
            entradas=int(row.entradas or 0),
            salidas=int(row.salidas or 0),
        )
        for row in rows
    ]
