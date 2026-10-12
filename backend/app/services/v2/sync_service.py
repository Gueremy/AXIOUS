"""
app/services/v2/sync_service.py
Servicio de sincronización offline con manejo de idempotencia y aislamiento por movimiento (Fase 1C).
Procesa bloques de movimientos provenientes de PWA / almacenamiento local:
- Idempotencia estricta mediante uuid_local scoped por organización.
- Si un movimiento falla (por capacidad, stock o reglas), no aborta el lote completo.
- Retorna un resultado individual estructurado por cada movimiento procesado.
"""
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


class OfflineSyncService:

    @staticmethod
    async def procesar_lote_sync(
        db: AsyncSession,
        tenant: TenantContext,
        batch: SyncBatchRequest,
    ) -> SyncBatchResponse:
        resultados: List[SyncMovimientoResultado] = []
        sincronizados = 0
        rechazados = 0

        for item in batch.movimientos:
            # 1. Verificar idempotencia: ¿ya existe este uuid_local confirmado en la organización?
            stmt_dup = select(MovimientoV2).where(
                MovimientoV2.id_organizacion == tenant.id_organizacion,
                MovimientoV2.uuid_local == item.uuid_local,
            )
            dup = (await db.execute(stmt_dup)).scalar_one_or_none()
            if dup:
                resultados.append(
                    SyncMovimientoResultado(
                        uuid_local=item.uuid_local,
                        estado="duplicado",
                        id_movimiento=dup.id,
                        motivo="Movimiento ya sincronizado previamente",
                    )
                )
                sincronizados += 1
                continue

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
                        auto_commit=False,
                    )

                    # Si el tipo requería aprobación pero se envió desde offline sync de supervisor,
                    # o si ya fue confirmado:
                    stmt_mov = select(MovimientoV2).where(
                        MovimientoV2.id_organizacion == tenant.id_organizacion,
                        MovimientoV2.uuid_local == item.uuid_local,
                    )
                    mov_creado = (await db.execute(stmt_mov)).scalar_one_or_none()
                    id_mov = mov_creado.id if mov_creado else solicitud.id

                await db.commit()

                resultados.append(
                    SyncMovimientoResultado(
                        uuid_local=item.uuid_local,
                        estado="sincronizado",
                        id_movimiento=id_mov,
                        motivo=None,
                    )
                )
                sincronizados += 1

            except HTTPException as exc:
                resultados.append(
                    SyncMovimientoResultado(
                        uuid_local=item.uuid_local,
                        estado="rechazado",
                        id_movimiento=None,
                        motivo=str(exc.detail),
                    )
                )
                rechazados += 1
            except Exception as exc:
                resultados.append(
                    SyncMovimientoResultado(
                        uuid_local=item.uuid_local,
                        estado="rechazado",
                        id_movimiento=None,
                        motivo=f"Error inesperado al sincronizar: {str(exc)}",
                    )
                )
                rechazados += 1

        return SyncBatchResponse(
            total=len(batch.movimientos),
            sincronizados=sincronizados,
            rechazados=rechazados,
            resultados=resultados,
        )
