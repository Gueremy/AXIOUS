"""Reacciones de la importación a eventos de conciliación."""
from sqlalchemy import select

from app.core.events.event_bus import DomainEvent
from app.database import AsyncSessionLocal
from app.models.v2.alerta import AlertaV2, ReglaAlertaV2
from app.models.v2.ubicacion import Ubicacion
from app.models.v2.zona import Zona
from app.modules.importacion.models import ImportacionJob, Inconsistencia
from app.services.v2.alerta_service import AlertaServiceV2


async def alertar_conciliacion(evento: DomainEvent) -> None:
    job_id = evento.payload.get("id_job")
    if not job_id or not evento.payload.get("inconsistencias"):
        return
    async with AsyncSessionLocal() as db:
        job = (await db.execute(select(ImportacionJob).where(
            ImportacionJob.id == job_id,
            ImportacionJob.id_organizacion == evento.id_organizacion,
        ))).scalar_one_or_none()
        if not job:
            return
        await AlertaServiceV2.inicializar_plantillas(db, evento.id_organizacion)
        regla = (await db.execute(select(ReglaAlertaV2).where(
            ReglaAlertaV2.id_organizacion == evento.id_organizacion,
            ReglaAlertaV2.codigo == "discrepancia_inventario",
            ReglaAlertaV2.habilitada.is_(True),
        ))).scalar_one_or_none()
        if not regla:
            await db.commit()
            return
        activas = (await db.execute(select(AlertaV2).where(
            AlertaV2.id_organizacion == evento.id_organizacion,
            AlertaV2.id_regla == regla.id,
            AlertaV2.estado == "activa",
        ))).scalars().all()
        stmt_inc = select(Inconsistencia.id_ubicacion, Zona.id_sitio).outerjoin(
            Ubicacion, Inconsistencia.id_ubicacion == Ubicacion.id,
        ).outerjoin(Zona, Ubicacion.id_zona == Zona.id).where(
            Inconsistencia.id_importacion_job == job_id,
            Inconsistencia.id_organizacion == evento.id_organizacion,
        )
        por_sitio: dict[str | None, tuple[int, str | None]] = {}
        for id_ubicacion, id_sitio in (await db.execute(stmt_inc)).all():
            cantidad, primera_ubicacion = por_sitio.get(id_sitio, (0, id_ubicacion))
            por_sitio[id_sitio] = (cantidad + 1, primera_ubicacion)
        for id_sitio, (cantidad, id_ubicacion) in por_sitio.items():
            if any((alerta.metadatos or {}).get("id_job") == job_id and
                   alerta.id_sitio == id_sitio for alerta in activas):
                continue
            db.add(AlertaV2(
                id_organizacion=evento.id_organizacion, id_regla=regla.id,
                id_sitio=id_sitio, id_ubicacion=id_ubicacion,
                tipo=regla.codigo, severidad=regla.severidad,
                titulo="Discrepancias en conciliación de inventario",
                descripcion=f"La importación {job.nombre_archivo} detectó {cantidad} inconsistencias en este sitio.",
                estado="activa", metadatos={"id_job": job_id},
            ))
        await db.commit()
