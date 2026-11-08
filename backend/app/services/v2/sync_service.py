"""
app/services/v2/sync_service.py
Servicio de sincronización offline con manejo de idempotencia y aislamiento por movimiento (Fase 1C).
Procesa bloques de movimientos provenientes de PWA / almacenamiento local:
- Idempotencia estricta mediante uuid_local scoped por organización.
- Si un movimiento falla (por capacidad, stock o reglas), no aborta el lote completo.
- Retorna un resultado individual estructurado por cada movimiento procesado.
"""
import logging
from typing import List
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies_v2 import TenantContext
from app.models.v2.movimiento import MovimientoV2
from app.schemas.v2.sync import (
    SyncBatchRequest,
    SyncBatchResponse,
    SyncMovimientoResultado,
)
from app.services.v2.movimiento_service import MovimientoService
from app.services.v2.alerta_service import AlertaServiceV2


class OfflineSyncService:

    @staticmethod
    async def procesar_lote_sync(
        db: AsyncSession,
        tenant: TenantContext,
        batch: SyncBatchRequest,
    ) -> SyncBatchResponse:
        resultados: List[SyncMovimientoResultado] = []
        sincronizados = 0
        pendientes = 0
        rechazados = 0
        reintentables = 0

        for item in batch.movimientos:
            # 1. Verificar idempotencia: ¿ya existe este uuid_local confirmado en la organización?
            stmt_dup = select(MovimientoV2).where(
                MovimientoV2.id_organizacion == tenant.id_organizacion,
                MovimientoV2.uuid_local == item.uuid_local,
            )
            dup = (await db.execute(stmt_dup)).scalar_one_or_none()
            # 2. Procesar con savepoint aislado por elemento
            try:
                async with db.begin_nested():
                    solicitud = await MovimientoService.crear_solicitud(
                        db=db,
                        tenant=tenant,
                        id_tipo_movimiento=item.id_tipo_movimiento,
                        id_item=item.id_item,
                        cantidad=item.cantidad,
                        unidad_medida=item.unidad_medida,
                        id_lote=item.id_lote,
                        id_ubicacion_origen=item.id_ubicacion_origen,
                        id_ubicacion_destino=item.id_ubicacion_destino,
                        observaciones=item.observaciones,
                        uuid_local=item.uuid_local,
                        atributos=item.atributos,
                        lote_nuevo=item.lote_nuevo,
                        fecha_hora_local=item.fecha_hora_local,
                        id_movimiento_original=item.id_movimiento_original,
                        auto_commit=False,
                    )

                    # Si el tipo requería aprobación pero se envió desde offline sync de supervisor,
                    # o si ya fue confirmado:
                    stmt_mov = select(MovimientoV2).where(
                        MovimientoV2.id_organizacion == tenant.id_organizacion,
                        MovimientoV2.uuid_local == item.uuid_local,
                    )
                    mov_creado = (await db.execute(stmt_mov)).scalar_one_or_none()
                    id_mov = mov_creado.id if mov_creado else None

                await db.commit()
                if mov_creado is not None:
                    try:
                        await MovimientoService.publicar_movimiento_confirmado(db, tenant, mov_creado)
                    except Exception:
                        logging.getLogger(__name__).exception("Fallo de notificación después de confirmar movimiento")

                resultados.append(
                    SyncMovimientoResultado(
                        uuid_local=item.uuid_local,
                        estado=("duplicado" if dup else "sincronizado") if id_mov else "pendiente",
                        id_movimiento=id_mov,
                        id_solicitud=solicitud.id,
                        motivo=None,
                    )
                )
                if id_mov:
                    sincronizados += 1
                else:
                    pendientes += 1

            except HTTPException as exc:
                if 400 <= exc.status_code < 500 and exc.status_code not in (408, 429):
                    await AlertaServiceV2.registrar_rechazo_sync(
                        db, tenant, item.uuid_local, str(exc.detail),
                        item.id_ubicacion_origen, item.id_ubicacion_destino, exc.status_code,
                    )
                resultados.append(
                    SyncMovimientoResultado(
                        uuid_local=item.uuid_local,
                        estado="reintentar" if exc.status_code >= 500 or exc.status_code in (408, 429) else "rechazado",
                        id_movimiento=None,
                        motivo="Servicio temporalmente no disponible; vuelve a sincronizar" if exc.status_code >= 500 else str(exc.detail),
                    )
                )
                if exc.status_code >= 500 or exc.status_code in (408, 429):
                    reintentables += 1
                else:
                    rechazados += 1
            except Exception as exc:
                resultados.append(
                    SyncMovimientoResultado(
                        uuid_local=item.uuid_local,
                        estado="reintentar",
                        id_movimiento=None,
                        motivo="No se pudo confirmar la operación. Vuelve a sincronizar con el mismo identificador.",
                    )
                )
                reintentables += 1

        return SyncBatchResponse(
            total=len(batch.movimientos),
            sincronizados=sincronizados,
            pendientes=pendientes,
            rechazados=rechazados,
            reintentables=reintentables,
            resultados=resultados,
        )
