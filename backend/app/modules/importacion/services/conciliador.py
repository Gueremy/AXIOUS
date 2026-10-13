"""
app/modules/importacion/services/conciliador.py
Motor de conciliación ERP/WMS (Fase 1E).
Detecta sobrecapacidad, mezclas de lotes no permitidas, ubicaciones inexistentes,
e ítems incompatibles sin modificar silenciosamente los datos.
"""
from decimal import Decimal
from typing import Any, Dict, List, Optional
import uuid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies_v2 import TenantContext
from app.core.site_access import allowed_location_ids
from app.models.log_auditoria import LogAuditoria
from app.models.v2.item import Item
from app.models.v2.lote import Lote
from app.models.v2.regla_ubicacion import ReglaUbicacion
from app.models.v2.saldo_stock import SaldoStock
from app.models.v2.sitio import Sitio
from app.models.v2.ubicacion import Ubicacion
from app.models.v2.zona import Zona
from app.modules.importacion.models import ImportacionJob, Inconsistencia


class ConciliadorService:

    @staticmethod
    async def conciliar(
        db: AsyncSession,
        tenant: TenantContext,
        nombre_archivo: str,
        tipo_fuente: str,
        filas_normalizadas: List[Dict[str, Any]],
        id_mapping_profile: Optional[str] = None,
    ) -> ImportacionJob:
        """
        Ejecuta la conciliación completa registrando el job y las inconsistencias detectadas.
        """
        job = ImportacionJob(
            id=str(uuid.uuid4()),
            id_organizacion=tenant.id_organizacion,
            id_mapping_profile=id_mapping_profile,
            id_usuario=tenant.usuario.id,
            nombre_archivo=nombre_archivo,
            tipo_fuente=tipo_fuente,
            estado="procesando",
            total_registros=len(filas_normalizadas),
        )
        db.add(job)
        await db.flush()

        # 1. Cargar catálogo de ubicaciones, ítems y saldos actuales de la organización
        stmt_ubis = select(Ubicacion, Sitio.codigo, Zona.codigo).join(
            Zona, Ubicacion.id_zona == Zona.id,
        ).join(Sitio, Zona.id_sitio == Sitio.id).where(
            Ubicacion.id_organizacion == tenant.id_organizacion,
            Ubicacion.activo == True,
        )
        if tenant.sitios_permitidos is not None:
            stmt_ubis = stmt_ubis.where(Ubicacion.id.in_(allowed_location_ids(tenant)))
        ubis: Dict[str, list] = {}
        for ubi, sitio_codigo, zona_codigo in (await db.execute(stmt_ubis)).all():
            ubis.setdefault(ubi.codigo, []).append((ubi, sitio_codigo, zona_codigo))

        stmt_items = select(Item).where(
            Item.id_organizacion == tenant.id_organizacion,
            Item.activo == True,
        )
        items = {i.codigo: i for i in (await db.execute(stmt_items)).scalars().all()}

        # Reglas de ubicación específicas
        stmt_reglas = select(ReglaUbicacion).where(
            ReglaUbicacion.id_organizacion == tenant.id_organizacion,
            ReglaUbicacion.activo == True,
        )
        reglas_list = (await db.execute(stmt_reglas)).scalars().all()
        reglas_por_ubi: Dict[str, List[ReglaUbicacion]] = {}
        for r in reglas_list:
            if r.id_ubicacion:
                reglas_por_ubi.setdefault(r.id_ubicacion, []).append(r)

        # Saldos existentes para validar mezcla de lotes
        stmt_saldos = select(SaldoStock, Lote.numero_lote).outerjoin(
            Lote, SaldoStock.id_lote == Lote.id
        ).where(
            SaldoStock.id_organizacion == tenant.id_organizacion,
            SaldoStock.cantidad > 0,
        )
        saldos_res = await db.execute(stmt_saldos)
        lotes_por_ubi: Dict[str, set] = {}
        for s, num_lote in saldos_res.all():
            if num_lote:
                lotes_por_ubi.setdefault(s.id_ubicacion, set()).add(num_lote)

        inconsistencias: List[Inconsistencia] = []

        # 2. Evaluar cada registro normalizado
        for item_norm in filas_normalizadas:
            fila_num = item_norm["fila"]
            cod_ubi = item_norm["codigo_ubicacion"]
            cod_sitio = item_norm.get("codigo_sitio")
            cod_zona = item_norm.get("codigo_zona")
            cod_item = item_norm["codigo_item"]
            num_lote = item_norm["numero_lote"]
            cant = item_norm["cantidad"]
            raw = item_norm["datos_crudos"]

            # Validación de datos obligatorios
            if not cod_ubi or not cod_item or cant is None or cant <= 0:
                inconsistencias.append(
                    Inconsistencia(
                        id_organizacion=tenant.id_organizacion,
                        id_importacion_job=job.id,
                        fila_origen=fila_num,
                        tipo_inconsistencia="datos_incompletos",
                        motivo="Faltan datos obligatorios (ubicación, ítem o cantidad válida)",
                        codigo_ubicacion=cod_ubi,
                        codigo_item=cod_item,
                        numero_lote=num_lote,
                        cantidad_externa=cant,
                        datos_crudos=raw,
                    )
                )
                continue

            # Validación: Ubicación inexistente
            candidates = [(ubi, site_code, zone_code) for ubi, site_code, zone_code in ubis.get(cod_ubi, [])
                          if (not cod_sitio or site_code == cod_sitio)
                          and (not cod_zona or zone_code == cod_zona)]
            if not candidates:
                inconsistencias.append(
                    Inconsistencia(
                        id_organizacion=tenant.id_organizacion,
                        id_importacion_job=job.id,
                        fila_origen=fila_num,
                        tipo_inconsistencia="ubicacion_inexistente",
                        motivo=f"La ubicación '{cod_ubi}' no existe en SalmoTrack",
                        codigo_ubicacion=cod_ubi,
                        codigo_item=cod_item,
                        numero_lote=num_lote,
                        cantidad_externa=cant,
                        datos_crudos=raw,
                    )
                )
                continue
            if len(candidates) > 1:
                inconsistencias.append(Inconsistencia(
                    id_organizacion=tenant.id_organizacion, id_importacion_job=job.id,
                    fila_origen=fila_num, tipo_inconsistencia="ubicacion_ambigua",
                    motivo=f"La ubicación '{cod_ubi}' es ambigua; indique codigo_sitio y codigo_zona",
                    codigo_ubicacion=cod_ubi, codigo_item=cod_item, numero_lote=num_lote,
                    cantidad_externa=cant, datos_crudos=raw,
                ))
                continue
            ubi = candidates[0][0]

            # Validación: Ítem inexistente
            item_obj = items.get(cod_item)
            if not item_obj:
                inconsistencias.append(
                    Inconsistencia(
                        id_organizacion=tenant.id_organizacion,
                        id_importacion_job=job.id,
                        fila_origen=fila_num,
                        tipo_inconsistencia="item_inexistente",
                        id_ubicacion=ubi.id,
                        motivo=f"El ítem '{cod_item}' no existe en el catálogo de la organización",
                        codigo_ubicacion=cod_ubi,
                        codigo_item=cod_item,
                        numero_lote=num_lote,
                        cantidad_externa=cant,
                        datos_crudos=raw,
                    )
                )
                continue

            # Validación: Sobrecapacidad
            if ubi.capacidad_maxima > 0:
                ocupacion_proyectada = ubi.ocupacion_actual + cant
                if ocupacion_proyectada > ubi.capacidad_maxima:
                    inconsistencias.append(
                        Inconsistencia(
                            id_organizacion=tenant.id_organizacion,
                            id_importacion_job=job.id,
                            fila_origen=fila_num,
                            tipo_inconsistencia="sobrecapacidad",
                            id_ubicacion=ubi.id,
                            motivo=(
                                f"La cantidad externa ({cant}) agregada a la ocupación actual "
                                f"({ubi.ocupacion_actual}) excede la capacidad máxima ({ubi.capacidad_maxima})"
                            ),
                            codigo_ubicacion=cod_ubi,
                            codigo_item=cod_item,
                            numero_lote=num_lote,
                            cantidad_externa=cant,
                            datos_crudos=raw,
                        )
                    )

            # Validación: Mezcla de lotes no permitida
            if not ubi.permite_mezcla_lotes and num_lote:
                lotes_existentes = lotes_por_ubi.get(ubi.id, set())
                if lotes_existentes and (num_lote not in lotes_existentes):
                    inconsistencias.append(
                        Inconsistencia(
                            id_organizacion=tenant.id_organizacion,
                            id_importacion_job=job.id,
                            fila_origen=fila_num,
                            tipo_inconsistencia="mezcla_lotes_no_permitida",
                            id_ubicacion=ubi.id,
                            motivo=(
                                f"La ubicación '{cod_ubi}' prohíbe mezclar lotes y ya contiene "
                                f"el lote '{list(lotes_existentes)[0]}', no compatible con '{num_lote}'"
                            ),
                            codigo_ubicacion=cod_ubi,
                            codigo_item=cod_item,
                            numero_lote=num_lote,
                            cantidad_externa=cant,
                            datos_crudos=raw,
                        )
                    )

            # Validación: Compatibilidad de categorías por ReglaUbicacion
            reglas_ubi = reglas_por_ubi.get(ubi.id, [])
            for r in reglas_ubi:
                if r.tipo_regla == "items_permitidos":
                    categorias_permitidas = r.configuracion.get("categorias_permitidas", [])
                    if categorias_permitidas and item_obj.categoria not in categorias_permitidas:
                        inconsistencias.append(
                            Inconsistencia(
                                id_organizacion=tenant.id_organizacion,
                                id_importacion_job=job.id,
                                fila_origen=fila_num,
                                tipo_inconsistencia="item_incompatible",
                                id_ubicacion=ubi.id,
                                motivo=(
                                    f"El ítem '{item_obj.codigo}' pertenece a la categoría '{item_obj.categoria}', "
                                    f"no permitida en '{cod_ubi}' (permitidas: {categorias_permitidas})"
                                ),
                                codigo_ubicacion=cod_ubi,
                                codigo_item=cod_item,
                                numero_lote=num_lote,
                                cantidad_externa=cant,
                                datos_crudos=raw,
                            )
                        )

        # 3. Guardar inconsistencias y consolidar job
        if inconsistencias:
            db.add_all(inconsistencias)

        total_reg = len(filas_normalizadas)
        total_inconsistencias = len(inconsistencias)
        job.registros_inconsistentes = total_inconsistencias
        job.registros_validos = total_reg - total_inconsistencias
        job.estado = "completado"
        job.fecha_fin = func.now()
        job.resumen = {
            "total": total_reg,
            "validos": job.registros_validos,
            "inconsistentes": total_inconsistencias,
            "porcentaje_consistencia": round((job.registros_validos / total_reg * 100), 2) if total_reg > 0 else 100.0,
        }

        auditoria = LogAuditoria(
            id_usuario=tenant.usuario.id,
            accion="CONCILIACION_ERP_EJECUTADA",
            entidad_afectada="v2_importacion_job",
            id_entidad=job.id,
            detalles=job.resumen,
        )
        db.add(auditoria)

        await db.commit()
        await db.refresh(job)
        return job
