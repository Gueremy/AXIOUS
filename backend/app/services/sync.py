"""
app/services/sync.py
AXI-13 — Sincronizacion offline real (Last-Write-Wins + validacion capacidad)

Recibe movimientos creados en Dexie.js mientras el dispositivo estaba offline
y los inserta en la BD si pasan la validacion de capacidad actual.
"""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.container import Container
from app.models.movimiento import Movimiento


def _resolver_conflicto(mov_offline: dict, container: Container) -> dict:
    """Last-Write-Wins con validacion de capacidad."""
    cantidad = Decimal(str(mov_offline["cantidad"]))
    tipo = mov_offline.get("tipo", "")

    if tipo in ("entrada_proveedor",):
        disponible = container.capacidad_max - container.ocupacion_actual
        if cantidad > disponible:
            return {
                "accion": "rechazar",
                "motivo": f"Sin capacidad. Disponible: {float(disponible):.2f}",
            }

    if tipo in ("salida_produccion", "traslado_interno"):
        if cantidad > container.ocupacion_actual:
            return {
                "accion": "rechazar",
                "motivo": f"Stock insuficiente. Actual: {float(container.ocupacion_actual):.2f}",
            }

    return {"accion": "aplicar", "motivo": "OK"}


async def procesar_sync(
    movimientos_offline: list[dict],
    id_usuario: str,
    db: AsyncSession,
) -> list[dict]:
    """
    Procesa cada movimiento offline:
    - Valida container existe y pertenece al usuario
    - Resuelve conflicto de capacidad (Last-Write-Wins)
    - Inserta en BD con origen='offline_sync' y estado='pendiente'
    - Devuelve lista de resultados por uuid_local
    """
    resultados = []

    for mov in movimientos_offline:
        uuid_local = mov.get("uuid_local", "sin-uuid")

        container = (
            await db.execute(
                select(Container).where(Container.id == mov.get("id_container"))
            )
        ).scalars().first()

        if not container:
            resultados.append({
                "uuid_local": uuid_local,
                "accion": "rechazar",
                "motivo": "Container no encontrado o eliminado.",
            })
            continue

        decision = _resolver_conflicto(mov, container)
        if decision["accion"] == "rechazar":
            resultados.append({"uuid_local": uuid_local, **decision})
            continue

        # Insertar movimiento real en BD
        nuevo = Movimiento(
            id=str(uuid.uuid4()),
            id_container=mov["id_container"],
            id_producto=mov["id_producto"],
            id_usuario=id_usuario,
            tipo=mov["tipo"],
            estado="pendiente",
            cantidad=Decimal(str(mov["cantidad"])),
            numero_lote=mov.get("numero_lote", "OFFLINE"),
            fecha_vencimiento=_parse_dt(mov.get("fecha_vencimiento")),
            nombre_proveedor=mov.get("nombre_proveedor"),
            num_guia_despacho=mov.get("num_guia_despacho"),
            registro_sanitario=mov.get("registro_sanitario"),
            temperatura_almacen=_parse_decimal(mov.get("temperatura_almacen")),
            observaciones=mov.get("observaciones"),
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


def _parse_dt(val) -> datetime | None:
    if not val:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_decimal(val) -> Decimal | None:
    if val is None:
        return None
    try:
        return Decimal(str(val))
    except Exception:
        return None
