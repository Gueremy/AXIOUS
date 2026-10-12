from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies_v2 import TenantContext, get_current_tenant
from app.core.modules.registry import ModuleRegistry
from app.database import get_db
from app.models.v2.item import Item
from app.models.v2.movimiento import MovimientoV2

router = APIRouter(prefix="/modulos/salmonero", tags=["V2 - Pack Acuícola Salmonero"])


@router.get("/reporte")
async def obtener_reporte_sernapesca(
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Genera el reporte regulatorio de acuicultura SERNAPESCA.
    Sólo está disponible si la organización tiene activo el 'pack_salmonero'.
    """
    if not await ModuleRegistry.is_enabled(db, tenant.id_organizacion, "pack_salmonero"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El módulo 'pack_salmonero' no está habilitado para su organización.",
        )

    stmt = (
        select(MovimientoV2, Item.codigo)
        .join(Item, MovimientoV2.id_item == Item.id)
        .where(MovimientoV2.id_organizacion == tenant.id_organizacion)
        .order_by(MovimientoV2.fecha_hora.desc())
        .limit(500)
    )
    res = await db.execute(stmt)

    registros = []
    for mov, item_codigo in res.all():
        attrs = mov.atributos or {}
        registros.append({
            "id_movimiento": mov.id,
            "fecha": mov.fecha_hora.strftime("%Y-%m-%d %H:%M"),
            "item_codigo": item_codigo,
            "cantidad_kg": float(mov.cantidad),
            "concesion_sernapesca": attrs.get("codigo_concesion_sernapesca", "N/A"),
            "autorizacion_sag": attrs.get("autorizacion_sag", "N/A"),
        })

    return {
        "modulo": "pack_salmonero",
        "normativa": "Ley General de Pesca y Acuicultura (SERNAPESCA / SAG)",
        "organizacion_id": tenant.id_organizacion,
        "total_registros": len(registros),
        "registros": registros,
    }
