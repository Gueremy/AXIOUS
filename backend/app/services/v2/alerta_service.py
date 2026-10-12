"""
app/services/v2/alerta_service.py
Servicio de gestión y evaluación de alertas basadas en reglas configurables (Fase 1D).
Permite parametrizar umbrales por organización sin tocar código, soportando
evaluación programada y manual con deduplicación de alertas activas.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional
import uuid
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies_v2 import TenantContext
from app.models.log_auditoria import LogAuditoria
from app.models.v2.alerta import AlertaV2, ReglaAlertaV2
from app.models.v2.lote import Lote
from app.models.v2.saldo_stock import SaldoStock
from app.models.v2.ubicacion import Ubicacion
from app.models.v2.zona import Zona
from app.schemas.v2.alerta import ReglaAlertaCreate, ReglaAlertaUpdate


PLANTILLAS_DEFAULT = [
    {
        "codigo": "capacidad_critica",
        "nombre": "Ubicación en Capacidad Crítica",
        "tipo": "capacidad",
        "severidad": "critica",
        "configuracion": {"umbral_porcentaje": 90.0},
    },
    {
        "codigo": "vencimiento_7_dias",
        "nombre": "Lote Próximo a Vencer (7 días)",
        "tipo": "vencimiento",
        "severidad": "critica",
        "configuracion": {"dias": 7},
    },
    {
        "codigo": "vencimiento_30_dias",
        "nombre": "Lote Próximo a Vencer (30 días)",
        "tipo": "vencimiento",
        "severidad": "aviso",
        "configuracion": {"dias": 30},
    },
    {
        "codigo": "stock_minimo",
        "nombre": "Stock por debajo del mínimo",
        "tipo": "stock",
        "severidad": "aviso",
        "configuracion": {"umbral_minimo": 10.0},
    },
    {
        "codigo": "sin_movimiento_30_dias",
        "nombre": "Stock sin movimiento por más de 30 días",
        "tipo": "inactividad",
        "severidad": "informativa",
        "configuracion": {"dias": 30},
    },
    {
        "codigo": "discrepancia_inventario",
        "nombre": "Discrepancia en Conciliación de Inventario",
        "tipo": "conciliacion",
        "severidad": "critica",
        "configuracion": {},
    },
]


class AlertaServiceV2:

    @staticmethod
    async def inicializar_plantillas(db: AsyncSession, id_organizacion: str) -> List[ReglaAlertaV2]:
        """Inicializa las reglas plantilla para una organización si aún no existen."""
        reglas_creadas = []
        for plantilla in PLANTILLAS_DEFAULT:
            stmt = select(ReglaAlertaV2).where(
                ReglaAlertaV2.id_organizacion == id_organizacion,
                ReglaAlertaV2.codigo == plantilla["codigo"],
            )
            existente = (await db.execute(stmt)).scalar_one_or_none()
            if not existente:
                nueva = ReglaAlertaV2(
                    id=str(uuid.uuid4()),
                    id_organizacion=id_organizacion,
                    codigo=plantilla["codigo"],
                    nombre=plantilla["nombre"],
                    tipo=plantilla["tipo"],
                    severidad=plantilla["severidad"],
                    configuracion=plantilla["configuracion"],
                    habilitada=True,
                )
                db.add(nueva)
                reglas_creadas.append(nueva)
        if reglas_creadas:
            await db.flush()
        return reglas_creadas

    @staticmethod
    async def evaluar_alertas(db: AsyncSession, id_organizacion: str) -> List[AlertaV2]:
        """
        Ejecuta las reglas habilitadas para la organización y genera alertas nuevas sin duplicar existentes.
        """
        # Asegurar reglas plantilla mínimas
        await AlertaServiceV2.inicializar_plantillas(db, id_organizacion)

        stmt_reglas = select(ReglaAlertaV2).where(
            ReglaAlertaV2.id_organizacion == id_organizacion,
            ReglaAlertaV2.habilitada == True,
        )
        reglas = (await db.execute(stmt_reglas)).scalars().all()
        nuevas_alertas: List[AlertaV2] = []

        now = datetime.now(timezone.utc)

        for regla in reglas:
            if regla.tipo == "capacidad":
                # Evaluar ubicaciones que superen el umbral de porcentaje configurado
                umbral = Decimal(str(regla.configuracion.get("umbral_porcentaje", 90.0)))
                stmt_ubis = (
                    select(Ubicacion, Zona.id_sitio)
                    .join(Zona, Ubicacion.id_zona == Zona.id)
                    .where(
                        Ubicacion.id_organizacion == id_organizacion,
                        Ubicacion.activo == True,
                        Ubicacion.capacidad_maxima > 0,
                    )
                )
                res_ubis = await db.execute(stmt_ubis)
                for ubi, id_sitio in res_ubis.all():
                    porcentaje = (ubi.ocupacion_actual / ubi.capacidad_maxima) * Decimal("100.0")
                    if porcentaje >= umbral:
                        # Verificar si ya existe alerta activa para esta ubicación y regla
                        stmt_dup = select(AlertaV2).where(
                            AlertaV2.id_organizacion == id_organizacion,
                            AlertaV2.id_regla == regla.id,
                            AlertaV2.id_ubicacion == ubi.id,
                            AlertaV2.estado == "activa",
                        )
                        if not (await db.execute(stmt_dup)).scalar_one_or_none():
                            alerta = AlertaV2(
                                id_organizacion=id_organizacion,
                                id_regla=regla.id,
                                id_sitio=id_sitio,
                                id_ubicacion=ubi.id,
                                tipo=regla.codigo,
                                severidad=regla.severidad,
                                titulo=f"Capacidad crítica en {ubi.codigo} ({porcentaje:.1f}%)",
                                descripcion=(
                                    f"La ubicación {ubi.codigo} ha alcanzado un {porcentaje:.1f}% de ocupación "
                                    f"({ubi.ocupacion_actual}/{ubi.capacidad_maxima} {ubi.unidad_capacidad}), "
                                    f"superando el umbral del {umbral}%."
                                ),
                                estado="activa",
                                metadatos={"porcentaje_actual": float(porcentaje), "umbral": float(umbral)},
                            )
                            db.add(alerta)
                            nuevas_alertas.append(alerta)

            elif regla.tipo == "vencimiento":
                # Evaluar lotes con fecha de vencimiento dentro de la ventana de días
                dias = int(regla.configuracion.get("dias", 7))
                fecha_limite = now + timedelta(days=dias)

                stmt_lotes = select(Lote).where(
                    Lote.id_organizacion == id_organizacion,
                    Lote.fecha_vencimiento.isnot(None),
                    Lote.fecha_vencimiento <= fecha_limite,
                )
                lotes = (await db.execute(stmt_lotes)).scalars().all()
                for lote in lotes:
                    stmt_dup = select(AlertaV2).where(
                        AlertaV2.id_organizacion == id_organizacion,
                        AlertaV2.id_regla == regla.id,
                        AlertaV2.id_lote == lote.id,
                        AlertaV2.estado == "activa",
                    )
                    if not (await db.execute(stmt_dup)).scalar_one_or_none():
                        alerta = AlertaV2(
                            id_organizacion=id_organizacion,
                            id_regla=regla.id,
                            id_item=lote.id_item,
                            id_lote=lote.id,
                            tipo=regla.codigo,
                            severidad=regla.severidad,
                            titulo=f"Lote {lote.numero_lote} próximo a vencer",
                            descripcion=f"El lote {lote.numero_lote} vence el {lote.fecha_vencimiento.strftime('%Y-%m-%d')} (dentro de {dias} días).",
                            estado="activa",
                            metadatos={"fecha_vencimiento": lote.fecha_vencimiento.isoformat(), "dias_aviso": dias},
                        )
                        db.add(alerta)
                        nuevas_alertas.append(alerta)

            elif regla.tipo == "stock":
                # Evaluar saldos totales por ítem bajo el umbral mínimo
                umbral_min = Decimal(str(regla.configuracion.get("umbral_minimo", 10.0)))
                stmt_stock = (
                    select(SaldoStock.id_item, func.sum(SaldoStock.cantidad).label("total_stock"))
                    .where(SaldoStock.id_organizacion == id_organizacion)
                    .group_by(SaldoStock.id_item)
                    .having(func.sum(SaldoStock.cantidad) <= umbral_min)
                )
                for item_id, total_stock in (await db.execute(stmt_stock)).all():
                    stmt_dup = select(AlertaV2).where(
                        AlertaV2.id_organizacion == id_organizacion,
                        AlertaV2.id_regla == regla.id,
                        AlertaV2.id_item == item_id,
                        AlertaV2.estado == "activa",
                    )
                    if not (await db.execute(stmt_dup)).scalar_one_or_none():
                        alerta = AlertaV2(
                            id_organizacion=id_organizacion,
                            id_regla=regla.id,
                            id_item=item_id,
                            tipo=regla.codigo,
                            severidad=regla.severidad,
                            titulo=f"Stock bajo nivel mínimo para ítem",
                            descripcion=f"El ítem registra un stock acumulado de {total_stock}, bajo el umbral mínimo de {umbral_min}.",
                            estado="activa",
                            metadatos={"stock_actual": float(total_stock), "umbral_minimo": float(umbral_min)},
                        )
                        db.add(alerta)
                        nuevas_alertas.append(alerta)

        if nuevas_alertas:
            await db.flush()
        return nuevas_alertas

    @staticmethod
    async def revisar_alerta(
        db: AsyncSession,
        tenant: TenantContext,
        id_alerta: str,
        observaciones: Optional[str] = None,
    ) -> AlertaV2:
        stmt = select(AlertaV2).where(
            AlertaV2.id == id_alerta,
            AlertaV2.id_organizacion == tenant.id_organizacion,
        )
        alerta = (await db.execute(stmt)).scalar_one_or_none()
        if not alerta:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alerta no encontrada")

        alerta.estado = "revisada"
        alerta.id_usuario_revision = tenant.usuario.id
        alerta.fecha_revision = func.now()
        if observaciones:
            meta = dict(alerta.metadatos or {})
            meta["observaciones_revision"] = observaciones
            alerta.metadatos = meta

        auditoria = LogAuditoria(
            id_usuario=tenant.usuario.id,
            accion="REVISAR_ALERTA_V2",
            entidad_afectada="v2_alerta",
            id_entidad=alerta.id,
            detalles={"observaciones": observaciones},
        )
        db.add(auditoria)
        await db.commit()
        await db.refresh(alerta)
        return alerta

    @staticmethod
    async def resolver_alerta(
        db: AsyncSession,
        tenant: TenantContext,
        id_alerta: str,
        observaciones: Optional[str] = None,
    ) -> AlertaV2:
        stmt = select(AlertaV2).where(
            AlertaV2.id == id_alerta,
            AlertaV2.id_organizacion == tenant.id_organizacion,
        )
        alerta = (await db.execute(stmt)).scalar_one_or_none()
        if not alerta:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alerta no encontrada")

        alerta.estado = "resuelta"
        alerta.fecha_resolucion = func.now()
        if observaciones:
            meta = dict(alerta.metadatos or {})
            meta["observaciones_resolucion"] = observaciones
            alerta.metadatos = meta

        auditoria = LogAuditoria(
            id_usuario=tenant.usuario.id,
            accion="RESOLVER_ALERTA_V2",
            entidad_afectada="v2_alerta",
            id_entidad=alerta.id,
            detalles={"observaciones": observaciones},
        )
        db.add(auditoria)
        await db.commit()
        await db.refresh(alerta)
        return alerta
