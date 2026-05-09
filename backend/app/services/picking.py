"""
app/services/picking.py
AXI-21 — Optimizacion de ruta de picking

Algoritmo Nearest Neighbor con distancia Manhattan.
Complejidad O(n^2), aceptable para n < 50 containers/pedido.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.container import Container
from app.models.galpon import Galpon


def distancia_manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def optimizar_ruta(
    containers: list[dict],
    inicio: tuple[int, int] = (0, 0),
) -> dict:
    """
    Dado una lista de dicts con claves 'fila' y 'col',
    retorna la ruta optima usando Nearest Neighbor.
    """
    pendientes = [dict(c) for c in containers]
    ruta: list[dict] = []
    pos = inicio
    distancia_total = 0

    while pendientes:
        mas_cercano = min(
            pendientes,
            key=lambda c: distancia_manhattan(pos, (c["fila"], c["col"])),
        )
        dist = distancia_manhattan(pos, (mas_cercano["fila"], mas_cercano["col"]))
        mas_cercano["distancia_desde_anterior"] = dist
        distancia_total += dist
        ruta.append(mas_cercano)
        pos = (mas_cercano["fila"], mas_cercano["col"])
        pendientes.remove(mas_cercano)

    return {"ruta_optimizada": ruta, "distancia_total": distancia_total}


async def obtener_containers_para_picking(
    db: AsyncSession,
    ids_container: list[str],
    id_sede: str,
) -> list[dict]:
    """
    Recupera posicion y datos de los containers solicitados,
    validando que pertenezcan a la sede del usuario.
    """
    stmt = (
        select(
            Container.id,
            Container.codigo,
            Container.posicion_fila.label("fila"),
            Container.posicion_col.label("col"),
            Container.ocupacion_actual,
            Container.estado,
        )
        .join(Galpon, Container.id_galpon == Galpon.id)
        .where(
            Container.id.in_(ids_container),
            Galpon.id_sede == id_sede,
        )
    )
    rows = (await db.execute(stmt)).mappings().all()
    return [dict(row) for row in rows]
