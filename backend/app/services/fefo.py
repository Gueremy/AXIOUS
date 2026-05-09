"""
app/services/fefo.py
AXI-11 — FEFO: First Expired, First Out

Sugiere los containers con producto X ordenados por fecha_vencimiento ASC.
Objetivo: reducir mermas del 1.5% actual a < 1%.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

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
    """
    stmt = (
        select(
            Container.id,
            Container.codigo,
            Container.posicion_fila,
            Container.posicion_col,
            Container.ocupacion_actual,
            Container.capacidad_max,
            Movimiento.fecha_vencimiento,
            Movimiento.numero_lote,
        )
        .join(Movimiento, Movimiento.id_container == Container.id)
        .join(Galpon, Container.id_galpon == Galpon.id)
        .where(
            Movimiento.id_producto == id_producto,
            Galpon.id_sede == id_sede,
            Container.estado == "disponible",
            Movimiento.estado == "aprobado",
            Movimiento.fecha_vencimiento.isnot(None),
        )
        .order_by(Movimiento.fecha_vencimiento.asc())
        .limit(limite)
    )

    rows = (await db.execute(stmt)).mappings().all()
    return [dict(row) for row in rows]
