"""
app/modules/picking/service.py
Motor de picking configurable: FEFO, FIFO y LIFO (Fase 2E).
Opera sobre el modelo genérico de ubicación, ítem, lote y saldos de stock.
"""
from decimal import Decimal
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.v2.item import Item
from app.models.v2.lote import Lote
from app.models.v2.saldo_stock import SaldoStock
from app.models.v2.ubicacion import Ubicacion
from app.modules.picking.schemas import PickingPlanResponse, PickingSugerenciaItem


class PickingService:

    @staticmethod
    async def sugerir(
        db: AsyncSession,
        id_organizacion: str,
        id_item: str,
        cantidad_solicitada: Decimal,
        estrategia: str = "fefo",
    ) -> PickingPlanResponse:
        """
        Calcula el plan de picking óptimo según la estrategia solicitada:
        - fefo: First Expired, First Out (menor fecha_vencimiento)
        - fifo: First In, First Out (menor fecha_creacion de lote)
        - lifo: Last In, First Out (mayor fecha_creacion de lote)
        """
        estrategia = estrategia.lower()
        if estrategia not in ("fefo", "fifo", "lifo"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Estrategia '{estrategia}' inválida. Use 'fefo', 'fifo' o 'lifo'.",
            )

        if cantidad_solicitada <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La cantidad debe ser mayor a cero")

        # Verificar existencia del ítem en la organización
        stmt_item = select(Item).where(Item.id == id_item, Item.id_organizacion == id_organizacion)
        item = (await db.execute(stmt_item)).scalar_one_or_none()
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ítem no encontrado en la organización")

        # Consulta base de saldos disponibles con ubicación y lote
        stmt = (
            select(
                SaldoStock,
                Ubicacion.codigo.label("ubi_codigo"),
                Lote.numero_lote,
                Lote.fecha_vencimiento,
                Lote.fecha_creacion.label("lote_fecha_creacion"),
            )
            .join(Ubicacion, SaldoStock.id_ubicacion == Ubicacion.id)
            .outerjoin(Lote, SaldoStock.id_lote == Lote.id)
            .where(
                SaldoStock.id_organizacion == id_organizacion,
                SaldoStock.id_item == id_item,
                SaldoStock.cantidad > 0,
                Ubicacion.activo == True,
            )
        )

        # Aplicar orden según estrategia
        if estrategia == "fefo":
            stmt = stmt.order_by(Lote.fecha_vencimiento.asc().nulls_last(), SaldoStock.cantidad.desc())
        elif estrategia == "fifo":
            stmt = stmt.order_by(Lote.fecha_creacion.asc(), SaldoStock.cantidad.desc())
        else:  # lifo
            stmt = stmt.order_by(Lote.fecha_creacion.desc(), SaldoStock.cantidad.desc())

        res = await db.execute(stmt)
        filas = res.all()

        pendiente = cantidad_solicitada
        sugerencias: List[PickingSugerenciaItem] = []
        asignado = Decimal("0.0")

        for saldo, u_cod, num_lote, fecha_venc, _ in filas:
            if pendiente <= 0:
                break

            disponible = saldo.cantidad
            tomar = min(disponible, pendiente)

            sugerencias.append(
                PickingSugerenciaItem(
                    id_ubicacion=saldo.id_ubicacion,
                    codigo_ubicacion=u_cod,
                    id_lote=saldo.id_lote,
                    numero_lote=num_lote,
                    cantidad_disponible=disponible,
                    cantidad_sugerida=tomar,
                    fecha_vencimiento=fecha_venc,
                )
            )
            asignado += tomar
            pendiente -= tomar

        return PickingPlanResponse(
            estrategia=estrategia,
            id_item=id_item,
            cantidad_solicitada=cantidad_solicitada,
            cantidad_asignada=asignado,
            completado=(asignado >= cantidad_solicitada),
            sugerencias=sugerencias,
        )
