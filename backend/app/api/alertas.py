"""
app/api/alertas.py
Router CRUD de alertas — Sprint 3 (AXI-17).

Endpoints:
  GET  /alertas/activas       — Alertas activas de la sede del usuario
  GET  /alertas/historial     — Historial paginado de alertas de la sede
  PATCH /alertas/{id}/revisar — Cambia estado activa → revisada
  PATCH /alertas/{id}/resolver — Cambia estado revisada → resuelta

Reglas:
  - Aislamiento multi-sede SIEMPRE (excepto super_admin)
  - NUNCA exponer RUT (Ley 19.628)
  - Paginación eficiente con func.count()
  - Auditoría en cada PATCH
"""
import math
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.alerta import Alerta
from app.models.container import Container
from app.models.galpon import Galpon
from app.models.usuario import Usuario
from app.schemas.alerta import AlertaRead, AlertaRevisar, AlertaResolver
from app.core.dependencies import require_role
from app.core.audit import log_action
from app.core.logger import log_alerta_resuelta

router = APIRouter()

# ── Roles permitidos ──────────────────────────────────────────────────────────
ROLES_ALERTAS = ["jefe_bodega", "admin_sede", "super_admin"]


def _filtro_sede(stmt, current_user: Usuario):
    """Aplica aislamiento multi-sede (excepto super_admin)."""
    if current_user.rol != "super_admin" and current_user.id_sede:
        stmt = (
            stmt
            .join(Container, Alerta.id_container == Container.id)
            .join(Galpon, Container.id_galpon == Galpon.id)
            .where(Galpon.id_sede == current_user.id_sede)
        )
    return stmt


@router.get("/activas", response_model=list[AlertaRead])
async def get_alertas_activas(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role(ROLES_ALERTAS)),
) -> Any:
    """Retorna todas las alertas activas de la sede del usuario."""
    stmt = select(Alerta).where(Alerta.estado == "activa")
    stmt = _filtro_sede(stmt, current_user)
    stmt = stmt.order_by(Alerta.fecha_generacion.desc())

    result = await db.execute(stmt)
    alertas = result.scalars().all()
    return [AlertaRead.model_validate(a) for a in alertas]


@router.get("/historial")
async def get_alertas_historial(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    tipo: str = Query(None, description="Filtrar por tipo de alerta"),
    severidad: str = Query(None, description="Filtrar por severidad"),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role(ROLES_ALERTAS)),
) -> Any:
    """Historial paginado de alertas (todos los estados) de la sede."""
    # Base query para filtros
    base_where = []
    if tipo:
        base_where.append(Alerta.tipo == tipo)
    if severidad:
        base_where.append(Alerta.severidad == severidad)

    # COUNT eficiente (nunca len())
    count_stmt = select(func.count()).select_from(Alerta)
    for w in base_where:
        count_stmt = count_stmt.where(w)
    count_stmt = _filtro_sede(count_stmt, current_user)
    total = await db.scalar(count_stmt) or 0

    # Items paginados
    skip = (page - 1) * size
    items_stmt = select(Alerta)
    for w in base_where:
        items_stmt = items_stmt.where(w)
    items_stmt = _filtro_sede(items_stmt, current_user)
    items_stmt = items_stmt.order_by(Alerta.fecha_generacion.desc()).offset(skip).limit(size)

    result = await db.execute(items_stmt)
    alertas = result.scalars().all()

    return {
        "items": [AlertaRead.model_validate(a) for a in alertas],
        "total": total,
        "page": page,
        "size": size,
        "pages": math.ceil(total / size) if size > 0 else 0,
    }


@router.patch("/{id}/revisar", response_model=AlertaRead)
async def revisar_alerta(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role(ROLES_ALERTAS)),
) -> Any:
    """Marca una alerta activa como revisada."""
    alerta = (await db.execute(
        select(Alerta).where(Alerta.id == id)
    )).scalars().first()

    if not alerta:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")

    # Verificar aislamiento de sede
    if current_user.rol != "super_admin" and current_user.id_sede:
        container = (await db.execute(
            select(Container).where(Container.id == alerta.id_container)
        )).scalars().first()
        if container:
            galpon = (await db.execute(
                select(Galpon).where(Galpon.id == container.id_galpon)
            )).scalars().first()
            if galpon and galpon.id_sede != current_user.id_sede:
                raise HTTPException(status_code=403, detail="No tienes acceso a alertas de otra sede")

    if alerta.estado != "activa":
        raise HTTPException(
            status_code=400,
            detail=f"Solo se pueden revisar alertas activas. Estado actual: {alerta.estado}"
        )

    alerta.estado = "revisada"
    alerta.id_usuario_revision = current_user.id
    alerta.fecha_revision = datetime.now(timezone.utc)

    await log_action(
        db, current_user.id, "REVISAR_ALERTA", "Alerta", str(alerta.id),
        {"tipo": alerta.tipo, "severidad": alerta.severidad}
    )

    await db.commit()
    await db.refresh(alerta)
    return AlertaRead.model_validate(alerta)


@router.patch("/{id}/resolver", response_model=AlertaRead)
async def resolver_alerta(
    id: str,
    payload: AlertaResolver,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role(ROLES_ALERTAS)),
) -> Any:
    """Marca una alerta revisada como resuelta."""
    alerta = (await db.execute(
        select(Alerta).where(Alerta.id == id)
    )).scalars().first()

    if not alerta:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")

    # Verificar aislamiento de sede
    if current_user.rol != "super_admin" and current_user.id_sede:
        container = (await db.execute(
            select(Container).where(Container.id == alerta.id_container)
        )).scalars().first()
        if container:
            galpon = (await db.execute(
                select(Galpon).where(Galpon.id == container.id_galpon)
            )).scalars().first()
            if galpon and galpon.id_sede != current_user.id_sede:
                raise HTTPException(status_code=403, detail="No tienes acceso a alertas de otra sede")

    if alerta.estado != "revisada":
        raise HTTPException(
            status_code=400,
            detail=f"Solo se pueden resolver alertas revisadas. Estado actual: {alerta.estado}"
        )

    alerta.estado = "resuelta"

    detalles = {"tipo": alerta.tipo, "severidad": alerta.severidad}
    if payload.observacion:
        detalles["observacion"] = payload.observacion

    await log_action(
        db, current_user.id, "RESOLVER_ALERTA", "Alerta", str(alerta.id),
        detalles
    )

    await db.commit()
    await db.refresh(alerta)

    # Obtener nombre de sede para el log (best-effort)
    _sede_nombre = "Sede desconocida"
    _container = (await db.execute(
        select(Container).where(Container.id == alerta.id_container)
    )).scalars().first()
    _container_codigo = _container.codigo if _container else alerta.id_container
    if _container:
        _galpon = (await db.execute(
            select(Galpon).where(Galpon.id == _container.id_galpon)
        )).scalars().first()
        if _galpon:
            from app.models.sede import Sede as _Sede
            _sede = (await db.execute(
                select(_Sede).where(_Sede.id == _galpon.id_sede)
            )).scalars().first()
            if _sede:
                _sede_nombre = _sede.nombre

    log_alerta_resuelta(
        nombre_usuario=current_user.nombre,
        tipo_alerta=alerta.tipo,
        container_codigo=_container_codigo,
        sede_nombre=_sede_nombre,
    )

    return AlertaRead.model_validate(alerta)
