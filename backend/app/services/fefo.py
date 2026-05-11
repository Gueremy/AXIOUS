"""
app/services/fefo.py
AXI-11 — FEFO: First Expired, First Out

Sugiere los containers con producto X ordenados por fecha_vencimiento ASC.
Objetivo: reducir mermas del 1.5% actual a < 1%.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.container import Container
from app.models.galpon import Galpon
from app.models.movimiento import Movimiento


async def sugerir_container_fefo(
    db: AsyncSession,
    id_producto: str,
    id_sede: str,
    limite: int = 5,
) -> list[dict]:
    """
    Retorna los containers que tienen el producto dado, ordenados por
    fecha_vencimiento ASC (el que vence antes sale primero — FEFO).

    Solo considera movimientos aprobados y containers disponibles.
    Filtra por sede para garantizar aislamiento multi-sede.
    Usa subquery con func.min() para evitar duplicados cuando un container
    tiene múltiples movimientos aprobados con distintas fechas de vencimiento.
    """
    # Subquery: fecha_vencimiento más próxima por container para el producto dado
    subq = (
        select(
            Movimiento.id_container,
            func.min(Movimiento.fecha_vencimiento).label("min_vencimiento"),
        )
        .where(
            Movimiento.id_producto == id_producto,
            Movimiento.estado == "aprobado",
            Movimiento.fecha_vencimiento.isnot(None),
        )
        .group_by(Movimiento.id_container)
        .subquery()
    )

    stmt = (
        select(
            Container.id,
            Container.codigo,
            Container.posicion_fila,
            Container.posicion_col,
            Container.ocupacion_actual,
            Container.capacidad_max,
            subq.c.min_vencimiento.label("fecha_vencimiento"),
        )
        .join(subq, subq.c.id_container == Container.id)
        .join(Galpon, Container.id_galpon == Galpon.id)
        .where(
            Galpon.id_sede == id_sede,
            Container.estado == "disponible",
        )
        .order_by(subq.c.min_vencimiento.asc())
        .limit(limite)
    )

    rows = (await db.execute(stmt)).mappings().all()
    return [dict(row) for row in rows]
