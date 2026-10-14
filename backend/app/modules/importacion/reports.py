"""Proveedor de datos de conciliación para el núcleo de reportes."""
from sqlalchemy import func, select

from app.core.site_access import allowed_location_ids
from app.modules.importacion.models import ImportacionJob, Inconsistencia


async def report_provider(db, tenant, kind: str, **kwargs):
    if kind == "inconsistencias_count":
        stmt = select(func.count(Inconsistencia.id)).where(
            Inconsistencia.id_organizacion == tenant.id_organizacion,
            Inconsistencia.resuelto.is_(False),
        )
        if tenant.sitios_permitidos is not None:
            stmt = stmt.where(Inconsistencia.id_ubicacion.in_(allowed_location_ids(tenant)))
        return (await db.execute(stmt)).scalar_one()

    if kind in ("inconsistencias_recientes", "inconsistencias_bi"):
        stmt = select(Inconsistencia).where(
            Inconsistencia.id_organizacion == tenant.id_organizacion,
        )
        if tenant.sitios_permitidos is not None:
            stmt = stmt.where(Inconsistencia.id_ubicacion.in_(allowed_location_ids(tenant)))
        order = (Inconsistencia.fecha_deteccion.desc() if kind == "inconsistencias_recientes"
                 else Inconsistencia.fecha_deteccion.asc())
        return (await db.execute(stmt.order_by(order).limit(kwargs.get("limit", 5000)))).scalars().all()

    if kind in ("export_importaciones", "export_inconsistencias"):
        model = ImportacionJob if kind == "export_importaciones" else Inconsistencia
        stmt = select(model).where(model.id_organizacion == tenant.id_organizacion)
        if tenant.sitios_permitidos is not None:
            if model is ImportacionJob:
                stmt = stmt.where(ImportacionJob.id_usuario == tenant.usuario.id)
            else:
                stmt = stmt.where(Inconsistencia.id_ubicacion.in_(allowed_location_ids(tenant)))
        total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
        rows = (await db.execute(stmt.order_by(model.id)
                                 .offset(kwargs.get("offset", 0)).limit(kwargs.get("limit", 1000)))).scalars().all()
        return rows, total
    return None
