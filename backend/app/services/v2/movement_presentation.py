"""Readable projections; identifiers remain available for operations and auditing."""
from sqlalchemy import select, or_
from app.models.usuario import Usuario
from app.models.v2.item import Item
from app.models.v2.lote import Lote
from app.models.v2.ubicacion import Ubicacion
from app.models.v2.tipo_movimiento import TipoMovimiento
from app.schemas.v2.movimiento import SolicitudMovimientoRead, MovimientoV2Read


def filter_movement_search(stmt, model, query):
    if not query or not query.strip():
        return stmt
    pattern = f"%{query.strip()}%"
    user_field = getattr(model, "id_usuario_solicitante", None)
    if user_field is None:
        user_field = model.id_usuario
    return stmt.where(or_(
        model.id_item.in_(select(Item.id).where(or_(Item.nombre.ilike(pattern), Item.codigo.ilike(pattern)))),
        model.id_lote.in_(select(Lote.id).where(Lote.numero_lote.ilike(pattern))),
        model.id_ubicacion_origen.in_(select(Ubicacion.id).where(Ubicacion.codigo.ilike(pattern))),
        model.id_ubicacion_destino.in_(select(Ubicacion.id).where(Ubicacion.codigo.ilike(pattern))),
        user_field.in_(select(Usuario.id).where(Usuario.nombre.ilike(pattern))),
    ))


async def present_movements(db, rows, requests=False):
    if not rows:
        return []
    async def lookup(model, ids):
        ids = {value for value in ids if value}
        if not ids:
            return {}
        return {obj.id: obj for obj in (await db.execute(select(model).where(model.id.in_(ids)))).scalars()}
    items = await lookup(Item, [row.id_item for row in rows])
    lots = await lookup(Lote, [row.id_lote for row in rows])
    locations = await lookup(Ubicacion, [value for row in rows for value in (row.id_ubicacion_origen, row.id_ubicacion_destino)])
    users = await lookup(Usuario, [value for row in rows for value in (
        row.id_usuario_solicitante if requests else row.id_usuario, row.id_usuario_aprobador)])
    types = await lookup(TipoMovimiento, [row.id_tipo_movimiento for row in rows])
    schema = SolicitudMovimientoRead if requests else MovimientoV2Read
    results = []
    for row in rows:
        item, lot, kind = items.get(row.id_item), lots.get(row.id_lote), types.get(row.id_tipo_movimiento)
        author = users.get(row.id_usuario_solicitante if requests else row.id_usuario)
        approver = users.get(row.id_usuario_aprobador)
        origin, destination = locations.get(row.id_ubicacion_origen), locations.get(row.id_ubicacion_destino)
        results.append(schema.model_validate(row).model_copy(update={
            "item_nombre": item.nombre if item else None,
            "item_codigo": item.codigo if item else None,
            "numero_lote": lot.numero_lote if lot else None,
            "fecha_vencimiento": lot.fecha_vencimiento if lot else None,
            "tipo_codigo": kind.codigo if kind else None,
            "efecto_stock": kind.efecto_stock if kind else None,
            "tipo_nombre": kind.nombre if kind else None,
            "ubicacion_origen_codigo": origin.codigo if origin else None,
            "ubicacion_destino_codigo": destination.codigo if destination else None,
            "usuario_nombre": author.nombre if author else None,
            "aprobador_nombre": approver.nombre if approver else None,
        }))
    return results
