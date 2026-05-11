"""
app/services/alertas.py
Motor de evaluación de alertas — Sprint 3 (AXI-14).
Implementa los 8 tipos de alerta definidos en GUIDELINES.md.

Se ejecuta en 2 contextos:
  1. Inmediato: post-aprobación de cada movimiento (desde movimientos.py)
  2. Programado: via APScheduler (jobs nocturnos y periódicos)
"""
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import case, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import log_alerta_creada as _log_alerta_creada

from app.models.alerta import Alerta
from app.models.container import Container
from app.models.galpon import Galpon
from app.models.movimiento import Movimiento
from app.models.producto import Producto
from app.models.sede import Sede

logger = logging.getLogger(__name__)


def _as_comparable(ahora: datetime, reference: datetime) -> datetime:
    """
    Devuelve ahora con el mismo tzinfo que reference para permitir comparaciones.
    SQLite devuelve datetimes naive; PostgreSQL devuelve tz-aware.
    Si reference es naive, retorna ahora sin tzinfo (UTC implícito).
    Si reference es tz-aware, retorna ahora con tzinfo UTC.
    """
    if reference.tzinfo is None:
        return ahora.replace(tzinfo=None)
    return ahora if ahora.tzinfo is not None else ahora.replace(tzinfo=timezone.utc)


# ── Configuración de alertas (GUIDELINES.md líneas 499-508) ───────────────────
ALERTAS_CONFIG = {
    "capacidad_critica":        {"umbral_pct": 80,  "severidad": "critica"},
    "vencimiento_30_dias":      {"dias": 30,        "severidad": "aviso"},
    "vencimiento_7_dias":       {"dias": 7,         "severidad": "critica"},
    "stock_minimo":             {                    "severidad": "aviso"},
    "movimiento_fuera_horario": {"hora_ini": 6, "hora_fin": 22, "severidad": "aviso"},
    "discrepancia_inventario":  {"umbral_pct": 5,   "severidad": "aviso"},
    "sin_movimiento_30_dias":   {"dias": 30,        "severidad": "informativa"},
    "cuarentena_activa":        {                    "severidad": "critica"},
}


async def _crear_alerta_si_no_existe(
    db: AsyncSession,
    id_container: str,
    tipo: str,
    severidad: str,
    descripcion: str,
    container_codigo: str = "",
    galpon_nombre: str = "Galpón",
    sede_nombre: str = "Sede",
) -> Optional[Alerta]:
    """Crea alerta solo si no existe una activa del mismo tipo para el container."""
    existente = await db.scalar(
        select(func.count()).select_from(Alerta).where(
            Alerta.id_container == id_container,
            Alerta.tipo == tipo,
            Alerta.estado == "activa",
        )
    )
    if existente and existente > 0:
        return None  # Deduplicación: ya existe una activa

    alerta = Alerta(
        id_container=id_container,
        tipo=tipo,
        severidad=severidad,
        descripcion=descripcion,
        estado="activa",
    )
    db.add(alerta)
    await db.flush()
    logger.info(f"Alerta creada: tipo={tipo}, container={id_container}, sev={severidad}")
    _log_alerta_creada(
        tipo_alerta=tipo,
        container_codigo=container_codigo or id_container,
        galpon_nombre=galpon_nombre,
        sede_nombre=sede_nombre,
        detalle=descripcion,
    )
    return alerta


# ── Funciones de evaluación por tipo ──────────────────────────────────────────

async def _check_capacidad_critica(
    container: Container, db: AsyncSession
) -> Optional[Alerta]:
    """Tipo 1: container con ocupación >= 80%."""
    if container.capacidad_max is None or container.capacidad_max == 0:
        return None
    pct = (Decimal(str(container.ocupacion_actual or 0)) / Decimal(str(container.capacidad_max))) * 100
    if pct >= ALERTAS_CONFIG["capacidad_critica"]["umbral_pct"]:
        return await _crear_alerta_si_no_existe(
            db, container.id, "capacidad_critica", "critica",
            f"Container {container.codigo} al {pct:.0f}% de capacidad "
            f"({container.ocupacion_actual}/{container.capacidad_max} {container.unidad_medida}).",
            container_codigo=container.codigo,
        )
    return None


async def _check_vencimientos(
    container: Container, db: AsyncSession, ahora: datetime
) -> list[Alerta]:
    """Tipos 2-3: movimientos aprobados con fecha_vencimiento próxima."""
    alertas_creadas = []
    # Usar ahora naive para el filtro SQL (compatible con SQLite y PostgreSQL naive)
    ahora_naive = ahora.replace(tzinfo=None)
    # Buscar movimientos aprobados en este container con vencimiento futuro
    stmt = (
        select(Movimiento)
        .where(
            Movimiento.id_container == container.id,
            Movimiento.estado == "aprobado",
            Movimiento.fecha_vencimiento.isnot(None),
            Movimiento.fecha_vencimiento > ahora_naive,
        )
    )
    rows = (await db.execute(stmt)).scalars().all()

    for mov in rows:
        ahora_cmp = _as_comparable(ahora, mov.fecha_vencimiento)
        dias_restantes = (mov.fecha_vencimiento - ahora_cmp).days
        if dias_restantes <= 7:
            a = await _crear_alerta_si_no_existe(
                db, container.id, "vencimiento_7_dias", "critica",
                f"Lote {mov.numero_lote} en container {container.codigo} "
                f"vence en {dias_restantes} días ({mov.fecha_vencimiento.strftime('%d/%m/%Y')}).",
                container_codigo=container.codigo,
            )
            if a:
                alertas_creadas.append(a)
        elif dias_restantes <= 30:
            a = await _crear_alerta_si_no_existe(
                db, container.id, "vencimiento_30_dias", "aviso",
                f"Lote {mov.numero_lote} en container {container.codigo} "
                f"vence en {dias_restantes} días ({mov.fecha_vencimiento.strftime('%d/%m/%Y')}).",
                container_codigo=container.codigo,
            )
            if a:
                alertas_creadas.append(a)

    return alertas_creadas


async def _check_stock_minimo(
    container: Container, db: AsyncSession
) -> Optional[Alerta]:
    """Tipo 4: ocupación actual menor al stock mínimo del producto."""
    # Buscar el producto más reciente asociado a este container
    stmt = (
        select(Producto)
        .join(Movimiento, Movimiento.id_producto == Producto.id)
        .where(
            Movimiento.id_container == container.id,
            Movimiento.estado == "aprobado",
        )
        .order_by(Movimiento.fecha_hora.desc())
        .limit(1)
    )
    producto = (await db.execute(stmt)).scalars().first()
    if not producto or producto.stock_minimo is None:
        return None  # Sin stock mínimo definido → no evaluar

    ocupacion = Decimal(str(container.ocupacion_actual or 0))
    if ocupacion < Decimal(str(producto.stock_minimo)):
        return await _crear_alerta_si_no_existe(
            db, container.id, "stock_minimo", "aviso",
            f"Container {container.codigo}: stock actual ({ocupacion} {container.unidad_medida}) "
            f"por debajo del mínimo operacional ({producto.stock_minimo} {container.unidad_medida}) "
            f"del producto {producto.nombre}.",
            container_codigo=container.codigo,
        )
    return None


async def _check_fuera_horario(
    container: Container, db: AsyncSession, ahora: datetime
) -> Optional[Alerta]:
    """Tipo 5: movimiento registrado fuera de horario (antes de 6:00 o después de 22:00)."""
    config = ALERTAS_CONFIG["movimiento_fuera_horario"]
    hora = ahora.hour
    if hora < config["hora_ini"] or hora >= config["hora_fin"]:
        return await _crear_alerta_si_no_existe(
            db, container.id, "movimiento_fuera_horario", "aviso",
            f"Movimiento en container {container.codigo} registrado fuera de horario "
            f"({ahora.strftime('%H:%M')}). Horario permitido: "
            f"{config['hora_ini']:02d}:00 — {config['hora_fin']:02d}:00.",
            container_codigo=container.codigo,
        )
    return None


async def _check_discrepancia(
    container: Container, db: AsyncSession
) -> Optional[Alerta]:
    """Tipo 6: diferencia entre ocupación registrada y suma de movimientos > 5%."""
    # Query 1: entradas, salidas y traslados_salida en una sola pasada
    row = (await db.execute(
        select(
            func.coalesce(func.sum(
                case((Movimiento.tipo == "entrada_proveedor", Movimiento.cantidad), else_=0)
            ), 0).label("entradas"),
            func.coalesce(func.sum(
                case((Movimiento.tipo == "salida_produccion", Movimiento.cantidad), else_=0)
            ), 0).label("salidas"),
            func.coalesce(func.sum(
                case((Movimiento.tipo == "traslado_interno", Movimiento.cantidad), else_=0)
            ), 0).label("traslados_salida"),
        )
        .where(
            Movimiento.id_container == container.id,
            Movimiento.estado == "aprobado",
        )
    )).one()

    # Query 2: traslados donde este container es destino
    traslados_entrada = await db.scalar(
        select(func.coalesce(func.sum(Movimiento.cantidad), 0))
        .where(
            Movimiento.id_container_destino == container.id,
            Movimiento.estado == "aprobado",
            Movimiento.tipo == "traslado_interno",
        )
    ) or Decimal("0")

    esperado = (
        Decimal(str(row.entradas or 0))
        - Decimal(str(row.salidas or 0))
        - Decimal(str(row.traslados_salida or 0))
        + Decimal(str(traslados_entrada or 0))
    )
    actual = Decimal(str(container.ocupacion_actual or 0))

    if esperado == 0:
        return None

    diff_pct = abs(actual - esperado) / abs(esperado) * 100
    if diff_pct > ALERTAS_CONFIG["discrepancia_inventario"]["umbral_pct"]:
        return await _crear_alerta_si_no_existe(
            db, container.id, "discrepancia_inventario", "aviso",
            f"Container {container.codigo}: discrepancia de {diff_pct:.1f}% "
            f"entre ocupación registrada ({actual}) y calculada ({esperado}).",
            container_codigo=container.codigo,
        )
    return None


async def _check_sin_movimiento(
    container: Container, db: AsyncSession, ahora: datetime
) -> Optional[Alerta]:
    """Tipo 7: container sin movimiento en los últimos 30 días."""
    config = ALERTAS_CONFIG["sin_movimiento_30_dias"]
    umbral = ahora - timedelta(days=config["dias"])

    if container.ultimo_movimiento is None:
        # Nunca tuvo movimiento — generar alerta solo si tiene ocupación
        if container.ocupacion_actual and Decimal(str(container.ocupacion_actual)) > 0:
            return await _crear_alerta_si_no_existe(
                db, container.id, "sin_movimiento_30_dias", "informativa",
                f"Container {container.codigo}: tiene stock pero nunca registró movimiento.",
                container_codigo=container.codigo,
            )
        return None

    ahora_cmp = _as_comparable(ahora, container.ultimo_movimiento)
    umbral = ahora_cmp - timedelta(days=config["dias"])
    if container.ultimo_movimiento < umbral:
        dias = (ahora_cmp - container.ultimo_movimiento).days
        return await _crear_alerta_si_no_existe(
            db, container.id, "sin_movimiento_30_dias", "informativa",
            f"Container {container.codigo}: sin movimiento hace {dias} días "
            f"(último: {container.ultimo_movimiento.strftime('%d/%m/%Y')}).",
            container_codigo=container.codigo,
        )
    return None


async def _check_cuarentena(
    container: Container, db: AsyncSession
) -> Optional[Alerta]:
    """Tipo 8: container en estado cuarentena."""
    if container.estado == "cuarentena":
        return await _crear_alerta_si_no_existe(
            db, container.id, "cuarentena_activa", "critica",
            f"Container {container.codigo} en CUARENTENA. "
            f"Motivo: {container.motivo_estado or 'Sin motivo especificado'}.",
            container_codigo=container.codigo,
        )
    return None


# ── Función principal ─────────────────────────────────────────────────────────

async def evaluar_alertas(
    id_container: str,
    db: AsyncSession,
    manager=None,
    ahora: Optional[datetime] = None,
) -> list[Alerta]:
    """
    Motor de evaluación de alertas post-aprobación.

    Args:
        id_container: UUID del container a evaluar
        db: sesión async de BD
        manager: ConnectionManager de WebSockets (opcional, para broadcast)
        ahora: datetime para inyectar en tests (default: utcnow)

    Returns:
        Lista de alertas creadas (puede estar vacía)
    """
    if ahora is None:
        ahora = datetime.now(timezone.utc)

    container = (await db.execute(
        select(Container).where(Container.id == id_container)
    )).scalars().first()

    if not container:
        logger.warning(f"evaluar_alertas: container {id_container} no encontrado")
        return []

    alertas_creadas: list[Alerta] = []

    # 1. Capacidad crítica (inmediato post-aprobación)
    a = await _check_capacidad_critica(container, db)
    if a:
        alertas_creadas.append(a)

    # 2-3. Vencimientos (inmediato + cron nocturno)
    venc = await _check_vencimientos(container, db, ahora)
    alertas_creadas.extend(venc)

    # 4. Stock mínimo (inmediato + cada 30 min)
    a = await _check_stock_minimo(container, db)
    if a:
        alertas_creadas.append(a)

    # 5. Fuera de horario (inmediato)
    a = await _check_fuera_horario(container, db, ahora)
    if a:
        alertas_creadas.append(a)

    # 6. Discrepancia inventario (cada 30 min)
    a = await _check_discrepancia(container, db)
    if a:
        alertas_creadas.append(a)

    # 7. Sin movimiento 30 días (cron nocturno)
    a = await _check_sin_movimiento(container, db, ahora)
    if a:
        alertas_creadas.append(a)

    # 8. Cuarentena activa (inmediato)
    a = await _check_cuarentena(container, db)
    if a:
        alertas_creadas.append(a)

    # Commit las alertas y broadcast por WebSocket
    if alertas_creadas:
        await db.commit()

        if manager:
            # Obtener id_sede del container para broadcast
            galpon = (await db.execute(
                select(Galpon).where(Galpon.id == container.id_galpon)
            )).scalars().first()
            if galpon:
                for alerta in alertas_creadas:
                    await manager.broadcast_sede(galpon.id_sede, {
                        "evento": "nueva_alerta",
                        "alerta": {
                            "id": alerta.id,
                            "tipo": alerta.tipo,
                            "severidad": alerta.severidad,
                            "descripcion": alerta.descripcion,
                            "id_container": alerta.id_container,
                            "container_codigo": container.codigo,
                            "fecha_generacion": str(alerta.fecha_generacion),
                        }
                    })

    return alertas_creadas


async def evaluar_alertas_batch(
    db: AsyncSession,
    tipos: list[str],
    manager=None,
    ahora: Optional[datetime] = None,
):
    """
    Evaluación por lote para jobs del scheduler.
    Evalúa los tipos indicados para TODOS los containers activos.

    Args:
        db: sesión async de BD
        tipos: lista de tipos a evaluar (subset de ALERTAS_CONFIG keys)
        manager: ConnectionManager (opcional)
        ahora: datetime para override
    """
    if ahora is None:
        ahora = datetime.now(timezone.utc)

    containers = (await db.execute(
        select(Container).where(
            Container.estado.notin_(["mantenimiento"])
        )
    )).scalars().all()

    total_creadas = 0
    for container in containers:
        alertas = []
        if "vencimiento_7_dias" in tipos or "vencimiento_30_dias" in tipos:
            alertas.extend(await _check_vencimientos(container, db, ahora))
        if "sin_movimiento_30_dias" in tipos:
            a = await _check_sin_movimiento(container, db, ahora)
            if a:
                alertas.append(a)
        if "stock_minimo" in tipos:
            a = await _check_stock_minimo(container, db)
            if a:
                alertas.append(a)
        if "discrepancia_inventario" in tipos:
            a = await _check_discrepancia(container, db)
            if a:
                alertas.append(a)

        if alertas:
            await db.commit()
            total_creadas += len(alertas)

            if manager:
                galpon = (await db.execute(
                    select(Galpon).where(Galpon.id == container.id_galpon)
                )).scalars().first()
                if galpon:
                    for alerta in alertas:
                        await manager.broadcast_sede(galpon.id_sede, {
                            "evento": "nueva_alerta",
                            "alerta": {
                                "id": alerta.id,
                                "tipo": alerta.tipo,
                                "severidad": alerta.severidad,
                                "descripcion": alerta.descripcion,
                                "id_container": alerta.id_container,
                                "container_codigo": container.codigo,
                            }
                        })

    logger.info(f"evaluar_alertas_batch: {total_creadas} alertas creadas para {len(containers)} containers")
    return total_creadas
