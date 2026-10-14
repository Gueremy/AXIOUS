"""Alertas v2 disparadas por eventos de movimiento confirmados."""
from datetime import timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select

from app.core.events.event_bus import DomainEvent
from app.database import AsyncSessionLocal
from app.models.v2.alerta import AlertaV2, ReglaAlertaV2
from app.models.v2.movimiento import MovimientoV2
from app.models.v2.ubicacion import Ubicacion
from app.models.v2.zona import Zona
from app.services.v2.alerta_service import AlertaServiceV2


async def alertar_movimiento_fuera_horario(evento: DomainEvent) -> None:
    movimiento_id = evento.payload.get("id_movimiento")
    if not movimiento_id:
        return
    async with AsyncSessionLocal() as db:
        movimiento = (await db.execute(select(MovimientoV2).where(
            MovimientoV2.id == movimiento_id,
            MovimientoV2.id_organizacion == evento.id_organizacion,
        ))).scalar_one_or_none()
        if movimiento is None:
            return
        await AlertaServiceV2.inicializar_plantillas(db, evento.id_organizacion)
        regla = (await db.execute(select(ReglaAlertaV2).where(
            ReglaAlertaV2.id_organizacion == evento.id_organizacion,
            ReglaAlertaV2.codigo == "movimiento_fuera_horario",
            ReglaAlertaV2.habilitada.is_(True),
        ))).scalar_one_or_none()
        if regla is None:
            await db.commit()
            return
        config = regla.configuracion or {}
        try:
            zona_horaria = ZoneInfo(config.get("zona_horaria", "America/Santiago"))
        except ZoneInfoNotFoundError:
            zona_horaria = timezone.utc
        fecha = movimiento.fecha_hora
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)
        hora = fecha.astimezone(zona_horaria).hour
        inicio = int(config.get("hora_inicio", 6))
        fin = int(config.get("hora_fin", 22))
        dentro = inicio <= hora < fin if inicio < fin else hora >= inicio or hora < fin
        if dentro:
            await db.commit()
            return
        location_id = movimiento.id_ubicacion_destino or movimiento.id_ubicacion_origen
        id_sitio = None
        if location_id:
            id_sitio = (await db.execute(select(Zona.id_sitio).join(
                Ubicacion, Ubicacion.id_zona == Zona.id,
            ).where(Ubicacion.id == location_id,
                    Ubicacion.id_organizacion == evento.id_organizacion))).scalar_one_or_none()
        activas = (await db.execute(select(AlertaV2).where(
            AlertaV2.id_organizacion == evento.id_organizacion,
            AlertaV2.id_regla == regla.id,
            AlertaV2.estado == "activa",
        ))).scalars().all()
        if not any((alerta.metadatos or {}).get("id_movimiento") == movimiento_id for alerta in activas):
            db.add(AlertaV2(
                id_organizacion=evento.id_organizacion, id_regla=regla.id,
                id_sitio=id_sitio, id_ubicacion=location_id,
                id_item=movimiento.id_item, id_lote=movimiento.id_lote,
                tipo=regla.codigo, severidad=regla.severidad,
                titulo="Movimiento fuera de horario",
                descripcion=f"Movimiento confirmado a las {hora:02d}:00 fuera del horario configurado.",
                estado="activa", metadatos={"id_movimiento": movimiento_id, "hora_local": hora},
            ))
        await db.commit()
