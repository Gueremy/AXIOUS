"""
app/services/v2/reglas_service.py
Motor central de evaluación de reglas de ubicación (Fase 1B).
Elimina validaciones fijas y permite reglas configurables y persistentes:
- Sobrecapacidad
- Prohibición / permisión de mezcla de lotes
- Categorías e ítems permitidos
- Reglas dinámicas por organización, zona o ubicación
"""
from decimal import Decimal
from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.v2.item import Item
from app.models.v2.lote import Lote
from app.models.v2.regla_ubicacion import ReglaUbicacion
from app.models.v2.saldo_stock import SaldoStock
from app.models.v2.ubicacion import Ubicacion
from app.models.v2.zona import Zona
from app.services.v2.configuracion_operativa import ConfiguracionOperativa, convertir_cantidad


class ReglasUbicacionService:

    @staticmethod
    async def evaluar_ingreso(
        db: AsyncSession,
        id_organizacion: str,
        ubi_dest: Ubicacion,
        item: Item,
        lote: Optional[Lote],
        cantidad: Decimal,
        config: ConfiguracionOperativa,
    ) -> Decimal:
        """
        Evalúa de forma centralizada todas las reglas aplicables antes de permitir un ingreso o traslado.
        Lanza HTTPException con motivo estructurado si alguna regla no se cumple.
        """
        cantidad_ubicacion = convertir_cantidad(
            cantidad, item.unidad_medida, ubi_dest.unidad_capacidad, config,
        )
        # 1. Validación de Capacidad
        nueva_ocupacion = ubi_dest.ocupacion_actual + cantidad_ubicacion
        if nueva_ocupacion > ubi_dest.capacidad_maxima:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Capacidad superada en destino. Capacidad máxima: {ubi_dest.capacidad_maxima}, Ocupación actual: {ubi_dest.ocupacion_actual}, Ingreso solicitado: {cantidad_ubicacion} {ubi_dest.unidad_capacidad}",
            )

        # 2. Todas las dimensiones configuradas de una regla deben corresponder
        # al destino; una regla de sitio nunca se convierte en regla global.
        id_sitio = (await db.execute(select(Zona.id_sitio).where(
            Zona.id == ubi_dest.id_zona,
            Zona.id_organizacion == id_organizacion,
        ))).scalar_one()
        stmt_reglas = select(ReglaUbicacion).where(
            ReglaUbicacion.id_organizacion == id_organizacion,
            ReglaUbicacion.activo == True,
            or_(ReglaUbicacion.id_sitio.is_(None), ReglaUbicacion.id_sitio == id_sitio),
            or_(ReglaUbicacion.id_zona.is_(None), ReglaUbicacion.id_zona == ubi_dest.id_zona),
            or_(ReglaUbicacion.id_ubicacion.is_(None), ReglaUbicacion.id_ubicacion == ubi_dest.id),
        )
        res_reglas = await db.execute(stmt_reglas)
        reglas = res_reglas.scalars().all()

        for regla in reglas:
            if regla.tipo_regla != "capacidad":
                continue
            configuracion = regla.configuracion or {}
            limite = ubi_dest.capacidad_maxima
            if configuracion.get("maximo") is not None:
                limite = min(limite, Decimal(str(configuracion["maximo"])))
            if configuracion.get("umbral_porcentaje") is not None:
                limite = min(limite, ubi_dest.capacidad_maxima *
                             Decimal(str(configuracion["umbral_porcentaje"])) / Decimal("100"))
            if nueva_ocupacion > limite:
                raise HTTPException(status_code=400, detail=(
                    f"Regla de capacidad '{regla.codigo}' superada en '{ubi_dest.codigo}'. "
                    f"Límite: {limite} {ubi_dest.unidad_capacidad}"
                ))

        # Determinar si se prohíbe mezcla de lotes (por configuración de la ubicación o por regla activa)
        prohibe_mezcla = not ubi_dest.permite_mezcla_lotes
        for r in reglas:
            if r.tipo_regla == "mezcla_lotes":
                if r.configuracion.get("permite_mezcla") is False:
                    prohibe_mezcla = True

        # 3. Evaluación de Mezcla de Lotes
        if prohibe_mezcla:
            stmt_saldos = select(SaldoStock).where(
                SaldoStock.id_ubicacion == ubi_dest.id,
                SaldoStock.cantidad > 0,
            )
            res_saldos = await db.execute(stmt_saldos)
            saldos_existentes = res_saldos.scalars().all()

            for s in saldos_existentes:
                lote_id_solicitado = lote.id if lote else None
                # Si ya hay un lote distinto en la ubicación o un ítem distinto
                if s.id_lote != lote_id_solicitado or s.id_item != item.id:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Regla violada: la ubicación '{ubi_dest.codigo}' prohíbe la mezcla de diferentes lotes o ítems",
                    )

        # 4. Evaluación de Categorías Permitidas
        for r in reglas:
            if r.tipo_regla == "categorias_permitidas":
                categorias_permitidas = r.configuracion.get("categorias", [])
                if categorias_permitidas and item.categoria not in categorias_permitidas:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Regla violada: la categoría '{item.categoria}' no está permitida en la ubicación '{ubi_dest.codigo}'. Categorías permitidas: {categorias_permitidas}",
                    )

        # 5. Evaluación de Ítems Permitidos
        for r in reglas:
            if r.tipo_regla == "items_permitidos":
                items_permitidos = r.configuracion.get("items", [])
                if items_permitidos and item.codigo not in items_permitidos:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Regla violada: el ítem '{item.codigo}' no está permitido en la ubicación '{ubi_dest.codigo}'. Ítems permitidos: {items_permitidos}",
                    )
        return cantidad_ubicacion
