"""
app/services/v2/movimiento_service.py
Servicio central de movimientos y gestión transaccional segura del stock.
Ejecuta la confirmación en una única transacción:
- Bloqueos pesimistas ordenados determinísticamente para prevenir deadlocks.
- Validación de existencias en origen y capacidad máxima en destino.
- Actualización atómica de SaldoStock y ocupación de ubicaciones.
- Inserción en el libro inmutable MovimientoV2 y registro de auditoría.
"""
from decimal import Decimal
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies_v2 import TenantContext
from app.models.log_auditoria import LogAuditoria
from app.models.v2.item import Item
from app.models.v2.lote import Lote
from app.models.v2.movimiento import MovimientoV2
from app.models.v2.saldo_stock import SaldoStock
from app.models.v2.solicitud_movimiento import SolicitudMovimiento
from app.models.v2.tipo_movimiento import TipoMovimiento
from app.models.v2.ubicacion import Ubicacion
from app.services.v2.reglas_service import ReglasUbicacionService


class MovimientoService:

    @staticmethod
    async def crear_solicitud(
        db: AsyncSession,
        tenant: TenantContext,
        id_tipo_movimiento: str,
        id_item: str,
        cantidad: Decimal,
        unidad_medida: str,
        id_lote: Optional[str] = None,
        id_ubicacion_origen: Optional[str] = None,
        id_ubicacion_destino: Optional[str] = None,
        observaciones: Optional[str] = None,
        uuid_local: Optional[str] = None,
        atributos: Optional[dict] = None,
        auto_commit: bool = True,
    ) -> SolicitudMovimiento:
        """Valida y crea una solicitud de movimiento; si no requiere aprobación, la ejecuta de inmediato."""
        if cantidad <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La cantidad debe ser mayor a cero")

        # 1. Validar Tipo de Movimiento
        stmt_tipo = select(TipoMovimiento).where(
            TipoMovimiento.id == id_tipo_movimiento,
            TipoMovimiento.id_organizacion == tenant.id_organizacion,
            TipoMovimiento.activo == True,
        )
        tipo = (await db.execute(stmt_tipo)).scalar_one_or_none()
        if not tipo:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tipo de movimiento no encontrado o inactivo")

        # 2. Validar Ítem
        stmt_item = select(Item).where(
            Item.id == id_item,
            Item.id_organizacion == tenant.id_organizacion,
            Item.activo == True,
        )
        item = (await db.execute(stmt_item)).scalar_one_or_none()
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ítem no encontrado o inactivo")

        if item.unidad_medida != unidad_medida:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unidad de medida incompatible: el ítem usa '{item.unidad_medida}', se envió '{unidad_medida}'",
            )

        # 3. Validar Lote si se envía
        if id_lote:
            stmt_lote = select(Lote).where(
                Lote.id == id_lote,
                Lote.id_item == id_item,
                Lote.id_organizacion == tenant.id_organizacion,
            )
            lote = (await db.execute(stmt_lote)).scalar_one_or_none()
            if not lote:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lote no encontrado o no pertenece al ítem indicado")

        # 4. Validar Ubicaciones requeridas según el tipo
        if tipo.requiere_origen and not id_ubicacion_origen:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El tipo de movimiento exige ubicación de origen")
        if tipo.requiere_destino and not id_ubicacion_destino:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El tipo de movimiento exige ubicación de destino")

        if id_ubicacion_origen:
            stmt_orig = select(Ubicacion).where(
                Ubicacion.id == id_ubicacion_origen,
                Ubicacion.id_organizacion == tenant.id_organizacion,
                Ubicacion.activo == True,
            )
            ubi_orig = (await db.execute(stmt_orig)).scalar_one_or_none()
            if not ubi_orig:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ubicación de origen no encontrada o inactiva")

        if id_ubicacion_destino:
            stmt_dest = select(Ubicacion).where(
                Ubicacion.id == id_ubicacion_destino,
                Ubicacion.id_organizacion == tenant.id_organizacion,
                Ubicacion.activo == True,
            )
            ubi_dest = (await db.execute(stmt_dest)).scalar_one_or_none()
            if not ubi_dest:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ubicación de destino no encontrada o inactiva")

        # Verificar idempotencia si viene uuid_local
        if uuid_local:
            stmt_dup = select(SolicitudMovimiento).where(
                SolicitudMovimiento.id_organizacion == tenant.id_organizacion,
                SolicitudMovimiento.uuid_local == uuid_local,
            )
            dup = (await db.execute(stmt_dup)).scalar_one_or_none()
            if dup:
                return dup

        solicitud = SolicitudMovimiento(
            id_organizacion=tenant.id_organizacion,
            id_tipo_movimiento=tipo.id,
            id_item=item.id,
            id_lote=id_lote,
            id_ubicacion_origen=id_ubicacion_origen,
            id_ubicacion_destino=id_ubicacion_destino,
            id_usuario_solicitante=tenant.usuario.id,
            cantidad=cantidad,
            unidad_medida=unidad_medida,
            estado="pendiente",
            observaciones=observaciones,
            uuid_local=uuid_local,
            atributos=atributos or {},
        )
        db.add(solicitud)
        await db.flush()

        # Si el tipo no requiere aprobación, se aprueba y ejecuta inmediatamente
        if not tipo.requiere_aprobacion:
            solicitud.estado = "aprobada"
            solicitud.id_usuario_aprobador = tenant.usuario.id
            solicitud.fecha_resolucion = func.now()
            await MovimientoService._ejecutar_confirmacion_atomica(db, tenant, solicitud, tipo)

        if auto_commit:
            await db.commit()
            await db.refresh(solicitud)
        else:
            await db.flush()
        return solicitud

    @staticmethod
    async def aprobar_solicitud(
        db: AsyncSession,
        tenant: TenantContext,
        id_solicitud: str,
    ) -> MovimientoV2:
        """Aprueba una solicitud pendiente, actualizando atómicamente saldo y registrando el movimiento."""
        stmt = select(SolicitudMovimiento).where(
            SolicitudMovimiento.id == id_solicitud,
            SolicitudMovimiento.id_organizacion == tenant.id_organizacion,
        )
        solicitud = (await db.execute(stmt)).scalar_one_or_none()
        if not solicitud:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Solicitud de movimiento no encontrada")

        if solicitud.estado != "pendiente":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"La solicitud ya se encuentra en estado '{solicitud.estado}'",
            )

        stmt_tipo = select(TipoMovimiento).where(TipoMovimiento.id == solicitud.id_tipo_movimiento)
        tipo = (await db.execute(stmt_tipo)).scalar_one()

        movimiento = await MovimientoService._ejecutar_confirmacion_atomica(db, tenant, solicitud, tipo)

        solicitud.estado = "aprobada"
        solicitud.id_usuario_aprobador = tenant.usuario.id
        solicitud.fecha_resolucion = func.now()

        await db.commit()
        await db.refresh(movimiento)
        return movimiento

    @staticmethod
    async def rechazar_solicitud(
        db: AsyncSession,
        tenant: TenantContext,
        id_solicitud: str,
        motivo_rechazo: str,
    ) -> SolicitudMovimiento:
        """Rechaza una solicitud de movimiento preservándola intacta para auditoría."""
        stmt = select(SolicitudMovimiento).where(
            SolicitudMovimiento.id == id_solicitud,
            SolicitudMovimiento.id_organizacion == tenant.id_organizacion,
        )
        solicitud = (await db.execute(stmt)).scalar_one_or_none()
        if not solicitud:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Solicitud de movimiento no encontrada")

        if solicitud.estado != "pendiente":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No se puede rechazar una solicitud en estado '{solicitud.estado}'",
            )

        solicitud.estado = "rechazada"
        solicitud.motivo_rechazo = motivo_rechazo
        solicitud.id_usuario_aprobador = tenant.usuario.id
        solicitud.fecha_resolucion = func.now()

        await db.commit()
        await db.refresh(solicitud)
        return solicitud

    @staticmethod
    async def _ejecutar_confirmacion_atomica(
        db: AsyncSession,
        tenant: TenantContext,
        solicitud: SolicitudMovimiento,
        tipo: TipoMovimiento,
    ) -> MovimientoV2:
        """
        Núcleo transaccional:
        Adquiere bloqueos pesimistas ordenados, valida existencias y capacidades,
        actualiza saldos y emite el movimiento inmutable.
        """
        efecto = tipo.efecto_stock

        # 1. Bloqueo determinista de Ubicaciones involucradas (ordenadas por UUID para prevenir deadlocks)
        ubis_ids = sorted([u for u in [solicitud.id_ubicacion_origen, solicitud.id_ubicacion_destino] if u])
        ubis_map = {}
        for uid in ubis_ids:
            # En bases concurrentes (PostgreSQL), with_for_update bloquea la fila
            stmt_u = select(Ubicacion).where(Ubicacion.id == uid).with_for_update()
            res_u = await db.execute(stmt_u)
            ubis_map[uid] = res_u.scalar_one()

        ubi_orig = ubis_map.get(solicitud.id_ubicacion_origen)
        ubi_dest = ubis_map.get(solicitud.id_ubicacion_destino)

        # 2. Descuento en Origen (si aplica salida o traslado)
        if efecto in ("salida", "traslado"):
            if not ubi_orig:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ubicación origen requerida para este movimiento")

            # Buscar saldo específico por ítem y lote
            stmt_saldo = select(SaldoStock).where(
                SaldoStock.id_ubicacion == ubi_orig.id,
                SaldoStock.id_item == solicitud.id_item,
                SaldoStock.id_lote == solicitud.id_lote,
            ).with_for_update()
            saldo_orig = (await db.execute(stmt_saldo)).scalar_one_or_none()

            stock_disponible = saldo_orig.cantidad if saldo_orig else Decimal("0.0")
            if stock_disponible < solicitud.cantidad:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Stock insuficiente en origen. Disponible: {stock_disponible}, Solicitado: {solicitud.cantidad}",
                )

            saldo_orig.cantidad -= solicitud.cantidad
            ubi_orig.ocupacion_actual = max(Decimal("0.0"), ubi_orig.ocupacion_actual - solicitud.cantidad)

        # 3. Acreditación en Destino (si aplica entrada o traslado)
        if efecto in ("entrada", "traslado"):
            if not ubi_dest:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ubicación destino requerida para este movimiento")

            # Cargar item y lote para evaluación de reglas
            stmt_it = select(Item).where(Item.id == solicitud.id_item)
            item_obj = (await db.execute(stmt_it)).scalar_one()

            lote_obj = None
            if solicitud.id_lote:
                stmt_lt = select(Lote).where(Lote.id == solicitud.id_lote)
                lote_obj = (await db.execute(stmt_lt)).scalar_one_or_none()

            # Evaluación centralizada de reglas de ubicación
            await ReglasUbicacionService.evaluar_ingreso(
                db=db,
                id_organizacion=tenant.id_organizacion,
                ubi_dest=ubi_dest,
                item=item_obj,
                lote=lote_obj,
                cantidad=solicitud.cantidad,
            )

            # Buscar o crear saldo en destino
            stmt_saldo_dest = select(SaldoStock).where(
                SaldoStock.id_ubicacion == ubi_dest.id,
                SaldoStock.id_item == solicitud.id_item,
                SaldoStock.id_lote == solicitud.id_lote,
            ).with_for_update()
            saldo_dest = (await db.execute(stmt_saldo_dest)).scalar_one_or_none()

            if saldo_dest:
                saldo_dest.cantidad += solicitud.cantidad
            else:
                saldo_dest = SaldoStock(
                    id_organizacion=tenant.id_organizacion,
                    id_ubicacion=ubi_dest.id,
                    id_item=solicitud.id_item,
                    id_lote=solicitud.id_lote,
                    cantidad=solicitud.cantidad,
                    unidad_medida=solicitud.unidad_medida,
                )
                db.add(saldo_dest)

            ubi_dest.ocupacion_actual += solicitud.cantidad

        # 4. Registrar Movimiento Inmutable
        movimiento = MovimientoV2(
            id_organizacion=tenant.id_organizacion,
            id_solicitud=solicitud.id,
            id_tipo_movimiento=solicitud.id_tipo_movimiento,
            id_item=solicitud.id_item,
            id_lote=solicitud.id_lote,
            id_ubicacion_origen=solicitud.id_ubicacion_origen,
            id_ubicacion_destino=solicitud.id_ubicacion_destino,
            id_usuario=solicitud.id_usuario_solicitante,
            id_usuario_aprobador=solicitud.id_usuario_aprobador,
            cantidad=solicitud.cantidad,
            unidad_medida=solicitud.unidad_medida,
            efecto_stock=efecto,
            uuid_local=solicitud.uuid_local,
            atributos=solicitud.atributos,
            observaciones=solicitud.observaciones,
        )
        db.add(movimiento)
        await db.flush()

        # 5. Registro de Auditoría
        auditoria = LogAuditoria(
            id_usuario=tenant.usuario.id,
            accion="MOVIMIENTO_CONFIRMADO",
            entidad_afectada="v2_movimiento",
            id_entidad=movimiento.id,
            detalles={
                "tipo": tipo.codigo,
                "efecto": efecto,
                "cantidad": float(solicitud.cantidad),
                "item_id": solicitud.id_item,
                "lote_id": solicitud.id_lote,
            },
        )
        db.add(auditoria)

        return movimiento
