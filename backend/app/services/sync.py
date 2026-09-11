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
from app.models.producto import Producto
from app.schemas.movimiento import MovimientoOfflineCreate

INCOMPATIBLE = {
    "alimento": ["quimico", "veterinario"],
    "quimico": ["alimento", "veterinario"],
    "veterinario": ["alimento"],
}


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

        if mov.uuid_local:
            existente = (
                await db.execute(
                    select(Movimiento).where(Movimiento.uuid_local == mov.uuid_local)
                )
            ).scalars().first()
            if existente:
                resultados.append({
                    "uuid_local": uuid_local,
                    "accion": "aplicar",
                    "motivo": "Movimiento ya sincronizado",
                    "id_movimiento": existente.id,
                })
                continue

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

        producto = (
            await db.execute(select(Producto).where(Producto.id == mov.id_producto))
        ).scalars().first()
        if not producto:
            resultados.append({
                "uuid_local": uuid_local,
                "accion": "rechazar",
                "motivo": "Producto no encontrado.",
            })
            continue

        if producto.categoria in INCOMPATIBLE.get(container.tipo_producto_permitido, []):
            resultados.append({
                "uuid_local": uuid_local,
                "accion": "rechazar",
                "motivo": "El producto no es compatible con el tipo permitido por el container.",
            })
            continue

        if not mov.fecha_vencimiento:
            resultados.append({
                "uuid_local": uuid_local,
                "accion": "rechazar",
                "motivo": "Fecha de vencimiento requerida.",
            })
            continue

        if mov.tipo == "entrada_proveedor":
            required = (
                mov.fecha_fabricacion,
                mov.nombre_proveedor,
                mov.num_guia_despacho,
                mov.registro_sanitario,
                mov.temperatura_almacen,
            )
            if any(value is None or value == "" for value in required):
                resultados.append({
                    "uuid_local": uuid_local,
                    "accion": "rechazar",
                    "motivo": "Faltan campos obligatorios SERNAPESCA para la entrada.",
                })
                continue
            if producto.categoria == "veterinario" and (
                not mov.num_receta_retenida or not mov.num_autorizacion_sag
            ):
                resultados.append({
                    "uuid_local": uuid_local,
                    "accion": "rechazar",
                    "motivo": "Faltan campos obligatorios SAG para el producto veterinario.",
                })
                continue

        if mov.tipo == "traslado_interno":
            destino_stmt = (
                select(Container)
                .join(Galpon, Container.id_galpon == Galpon.id)
                .where(Container.id == mov.id_container_destino)
            )
            if id_sede:
                destino_stmt = destino_stmt.where(Galpon.id_sede == id_sede)
            destino = (await db.execute(destino_stmt)).scalars().first()
            if not destino or destino.id == container.id:
                resultados.append({
                    "uuid_local": uuid_local,
                    "accion": "rechazar",
                    "motivo": "Container destino no encontrado, sin acceso o igual al origen.",
                })
                continue
            disponible_destino = destino.capacidad_max - destino.ocupacion_actual
            if Decimal(str(mov.cantidad)) > disponible_destino:
                resultados.append({
                    "uuid_local": uuid_local,
                    "accion": "rechazar",
                    "motivo": f"Sin capacidad en destino. Disponible: {float(disponible_destino):.2f}",
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
            uuid_local=mov.uuid_local or None,
            tipo=mov.tipo,
            estado="pendiente",
            cantidad=Decimal(str(mov.cantidad)),
            numero_lote=mov.numero_lote or "OFFLINE",
            fecha_fabricacion=mov.fecha_fabricacion,
            fecha_vencimiento=mov.fecha_vencimiento,
            nombre_proveedor=mov.nombre_proveedor,
            num_guia_despacho=mov.num_guia_despacho,
            registro_sanitario=mov.registro_sanitario,
            temperatura_almacen=_to_decimal(mov.temperatura_almacen),
            num_receta_retenida=mov.num_receta_retenida,
            num_autorizacion_sag=mov.num_autorizacion_sag,
            id_container_destino=mov.id_container_destino,
            observaciones=mov.observaciones,
            origen="offline_sync",
        )
        db.add(nuevo)
        await db.flush()

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
