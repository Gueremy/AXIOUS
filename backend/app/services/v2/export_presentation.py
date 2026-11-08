"""Human-readable cells without exposing credentials or opaque foreign keys."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select
from app.models.v2 import Item, Lote, Ubicacion, Zona, Sitio, TipoMovimiento
from app.services.v2.movement_presentation import present_movements

LABELS = {
    "id": "Referencia de auditoría", "codigo": "Código", "nombre": "Nombre", "cantidad": "Cantidad",
    "unidad_medida": "Unidad", "fecha_hora": "Fecha y hora (Chile)", "fecha_creacion": "Fecha de registro (Chile)",
    "fecha_vencimiento": "Vencimiento", "fecha_fabricacion": "Fabricación", "numero_lote": "Lote",
    "id_ubicacion": "Ubicación", "id_ubicacion_origen": "Origen", "id_ubicacion_destino": "Destino",
    "id_item": "Producto", "id_lote": "Lote", "id_tipo_movimiento": "Tipo de movimiento",
    "id_sitio": "Sede", "id_zona": "Zona", "id_zona_padre": "Zona superior",
    "capacidad_maxima": "Capacidad máxima", "ocupacion_actual": "Ocupación actual", "unidad_capacidad": "Unidad de capacidad",
}


def readable_cell(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Sí" if value else "No"
    if isinstance(value, datetime):
        aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return aware.astimezone(ZoneInfo("America/Santiago")).strftime("%d-%m-%Y %H:%M:%S %z")
    if isinstance(value, dict):
        return "; ".join(f"{key.replace('_', ' ')}: {readable_cell(item)}" for key, item in value.items()
                         if not any(secret in key.lower() for secret in ("rut", "password", "token", "secret")))
    if isinstance(value, list):
        return ", ".join(readable_cell(item) for item in value)
    return str(value)


async def readable_export(db, tenant, resource, objects, fields):
    if resource in ("movimientos", "solicitudes", "bi-movimientos"):
        rows = await present_movements(db, objects, requests=resource == "solicitudes")
        headers = ["Referencia de auditoría", "Fecha y hora (Chile)", "Tipo", "Código producto", "Producto", "Lote", "Origen", "Destino", "Cantidad", "Unidad", "Operario", "Aprobador"]
        values = [[row.id, getattr(row, "fecha_hora", None) or row.fecha_creacion,
                   row.tipo_nombre, row.item_codigo, row.item_nombre, row.numero_lote,
                   row.ubicacion_origen_codigo, row.ubicacion_destino_codigo, row.cantidad,
                   row.unidad_medida, row.usuario_nombre, row.aprobador_nombre] for row in rows]
        return headers, [[readable_cell(value) for value in row] for row in values]
    mappings = {}
    references = {"id_item": (Item, "nombre"), "id_lote": (Lote, "numero_lote"),
                  "id_tipo_movimiento": (TipoMovimiento, "nombre"), "id_ubicacion": (Ubicacion, "codigo"),
                  "id_sitio": (Sitio, "codigo"), "id_zona": (Zona, "codigo"), "id_zona_padre": (Zona, "codigo")}
    for field, (model, label) in references.items():
        if field not in fields:
            continue
        ids = {getattr(row, field) for row in objects if getattr(row, field, None)}
        rows = (await db.execute(select(model).where(model.id_organizacion == tenant.id_organizacion, model.id.in_(ids)))).scalars()
        mappings[field] = {row.id: (f"{row.codigo} · {row.nombre}" if model is Item else getattr(row, label)) for row in rows}
    headers = [LABELS.get(field, field.replace("_", " ").capitalize()) for field in fields]
    values = [[readable_cell(mappings[field].get(getattr(row, field), "Sin referencia histórica"))
               if field in mappings and getattr(row, field) else readable_cell(getattr(row, field))
               for field in fields] for row in objects]
    return headers, values
