"""
app/services/sync.py
AXI-13 — Sincronizacion offline real (Last-Write-Wins + validacion capacidad)

Recibe movimientos creados en Dexie.js mientras el dispositivo estaba offline
y los inserta en la BD si pasan la validacion de capacidad actual.
"""
import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.container import Container
from app.models.galpon import Galpon
from app.models.movimiento import Movimiento
from app.schemas.movimiento import MovimientoOfflineCreate


def _resolver_conflicto(mov: MovimientoOfflineCreate, container: Container) -> dict:
    """Last-Write-Wins con validacion de capacidad."""
    cantidad = Decimal(str(mov.cantidad))

    if mov.tipo == "entrada_proveedor":
        disponible = container.capacidad_max - container.ocupacion_actual
        if cantidad > disponible:
            return {
                "accion": "rechazar",
                "motivo": f"Sin capacidad. Disponible: {float(disponible):.2f}",
            }

    if mov.tipo in ("salida_produccion", "traslado_interno"):
        if cantidad > container.ocupacion_actual:
            return {
                "accion": "rechazar",
                "motivo": f"Stock insuficiente. Actual: {float(container.ocupacion_actual):.2f}",
            }

    return {"accion": "aplicar", "motivo": "OK"}


async def procesar_sync(
    movimientos_offline: list[MovimientoOfflineCreate],
    id_usuario: str,
    id_sede: str | None,
    db: AsyncSession,
) -> list[dict]:
    """
    Procesa cada movimiento offline:
    - Valida container existe y pertenece a la sede del usuario (aislamiento multi-sede)
    - Resuelve conflicto de capacidad (Last-Write-Wins)
    - Inserta en BD con origen='offline_sync' y estado='pendiente'
    - Devuelve lista de resultados por uuid_local
    """
    resultados = []

    for mov in movimientos_offline:
        uuid_local = mov.uuid_local or "sin-uuid"

        stmt = (
            select(Container)
            .join(Galpon, Container.id_galpon == Galpon.id)
            .where(Container.id == mov.id_container)
        )
        if id_sede:
            stmt = stmt.where(Galpon.id_sede == id_sede)

        container = (await db.execute(stmt)).scalars().first()

        if not container:
            resultados.append({
                "uuid_local": uuid_local,
                "accion": "rechazar",
                "motivo": "Container no encontrado o sin acceso.",
            })
            continue

        decision = _resolver_conflicto(mov, container)
        if decision["accion"] == "rechazar":
            resultados.append({"uuid_local": uuid_local, **decision})
            continue

        nuevo = Movimiento(
            id=str(uuid.uuid4()),
            id_container=mov.id_container,
            id_producto=mov.id_producto,
            id_usuario=id_usuario,
            tipo=mov.tipo,
            estado="pendiente",
            cantidad=Decimal(str(mov.cantidad)),
            numero_lote=mov.numero_lote or "OFFLINE",
            fecha_vencimiento=mov.fecha_vencimiento,
            nombre_proveedor=mov.nombre_proveedor,
            num_guia_despacho=mov.num_guia_despacho,
            registro_sanitario=mov.registro_sanitario,
            temperatura_almacen=_to_decimal(mov.temperatura_almacen),
            observaciones=mov.observaciones,
            origen="offline_sync",
        )
        db.add(nuevo)

        resultados.append({
            "uuid_local": uuid_local,
            "accion": "aplicar",
            "motivo": "OK",
            "id_movimiento": nuevo.id,
        })

    await db.commit()
    return resultados


def _to_decimal(val) -> Decimal | None:
    if val is None:
        return None
    try:
        return Decimal(str(val))
    except Exception:
        return None
