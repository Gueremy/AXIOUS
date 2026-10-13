"""Resolución de sitio para recursos v2 antes de autorizar lecturas o cambios."""
from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies_v2 import TenantContext
from app.models.v2.ubicacion import Ubicacion
from app.models.v2.zona import Zona


async def require_zone_access(db: AsyncSession, tenant: TenantContext, zone_id: str) -> str:
    site_id = (await db.execute(select(Zona.id_sitio).where(
        Zona.id == zone_id, Zona.id_organizacion == tenant.id_organizacion,
    ))).scalar_one_or_none()
    if site_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zona no encontrada")
    tenant.exigir_acceso_sitio(site_id)
    return site_id


async def require_location_access(db: AsyncSession, tenant: TenantContext, location_id: str) -> str:
    site_id = (await db.execute(select(Zona.id_sitio).join(
        Ubicacion, Ubicacion.id_zona == Zona.id,
    ).where(
        Ubicacion.id == location_id,
        Ubicacion.id_organizacion == tenant.id_organizacion,
        Zona.id_organizacion == tenant.id_organizacion,
    ))).scalar_one_or_none()
    if site_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ubicación no encontrada")
    tenant.exigir_acceso_sitio(site_id)
    return site_id


def allowed_location_ids(tenant: TenantContext):
    """Subconsulta para filtrar ambos extremos de un movimiento por sitio."""
    stmt = select(Ubicacion.id).join(Zona, Ubicacion.id_zona == Zona.id).where(
        Ubicacion.id_organizacion == tenant.id_organizacion,
        Zona.id_organizacion == tenant.id_organizacion,
    )
    if tenant.sitios_permitidos is not None:
        stmt = stmt.where(Zona.id_sitio.in_(tenant.sitios_permitidos))
    return stmt


def scope_movement_query(stmt, tenant: TenantContext, model):
    """Oculta movimientos que tocan algún sitio fuera de la asignación del usuario."""
    if tenant.sitios_permitidos is None:
        return stmt
    locations = allowed_location_ids(tenant)
    return stmt.where(
        or_(model.id_ubicacion_origen.is_not(None), model.id_ubicacion_destino.is_not(None)),
        or_(model.id_ubicacion_origen.is_(None), model.id_ubicacion_origen.in_(locations)),
        or_(model.id_ubicacion_destino.is_(None), model.id_ubicacion_destino.in_(locations)),
    )


def scope_alert_query(stmt, tenant: TenantContext, model):
    """Las alertas sin sitio explícito sólo son visibles a roles globales."""
    if tenant.sitios_permitidos is None:
        return stmt
    return stmt.where(or_(
        model.id_sitio.in_(tenant.sitios_permitidos),
        model.id_ubicacion.in_(allowed_location_ids(tenant)),
    ))
