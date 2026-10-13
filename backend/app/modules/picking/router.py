from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies_v2 import TenantContext, get_current_tenant, require_permission
from app.core.audit import log_action
from app.core.modules.registry import require_module_enabled
from app.database import get_db
from app.models.v2.organizacion import Organizacion
from app.modules.picking.schemas import PickingPlanResponse
from app.modules.picking.service import PickingService

router = APIRouter(prefix="/picking", tags=["V2 - Picking (FEFO / FIFO / LIFO)"],
                   dependencies=[Depends(require_module_enabled("fefo")),
                                 Depends(require_permission("stock:read"))])


class PickingStrategyUpdate(BaseModel):
    estrategia: str


@router.get("/estrategia")
async def consultar_estrategia(tenant: TenantContext = Depends(get_current_tenant)):
    return {"estrategia": (tenant.organizacion.configuracion or {}).get("estrategia_picking", "fefo")}


@router.patch("/estrategia")
async def configurar_estrategia(data: PickingStrategyUpdate,
                                tenant: TenantContext = Depends(get_current_tenant),
                                db: AsyncSession = Depends(get_db)):
    if not tenant.tiene_permiso("rbac:manage"):
        raise HTTPException(status_code=403, detail="Permiso insuficiente")
    estrategia = data.estrategia.lower()
    if estrategia not in ("fefo", "fifo", "lifo"):
        raise HTTPException(status_code=400, detail="Estrategia inválida")
    org = (await db.execute(select(Organizacion).where(Organizacion.id == tenant.id_organizacion))).scalar_one()
    org.configuracion = {**(org.configuracion or {}), "estrategia_picking": estrategia}
    await log_action(db, tenant.usuario.id, "CONFIGURAR_PICKING_V2", "v2_organizacion",
                     org.id, {"estrategia": estrategia})
    await db.commit()
    return {"estrategia": estrategia}


@router.get("/sugerir", response_model=PickingPlanResponse)
async def sugerir_picking(
    id_item: str = Query(..., description="ID del ítem a extraer"),
    cantidad: Decimal = Query(..., gt=0, description="Cantidad total requerida"),
    estrategia: Optional[str] = Query(None, description="Estrategia: fefo, fifo, lifo; por defecto la configurada"),
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Calcula la sugerencia de ubicaciones y lotes para picking
    según la estrategia configurada (FEFO por vencimiento, FIFO por antigüedad, LIFO).
    """
    return await PickingService.sugerir(
        db=db,
        id_organizacion=tenant.id_organizacion,
        id_item=id_item,
        cantidad_solicitada=cantidad,
        estrategia=estrategia or (tenant.organizacion.configuracion or {}).get("estrategia_picking", "fefo"),
        sitios_permitidos=tenant.sitios_permitidos,
    )
