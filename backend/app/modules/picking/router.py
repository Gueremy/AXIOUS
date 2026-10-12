from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies_v2 import TenantContext, get_current_tenant
from app.database import get_db
from app.modules.picking.schemas import PickingPlanResponse
from app.modules.picking.service import PickingService

router = APIRouter(prefix="/picking", tags=["V2 - Picking (FEFO / FIFO / LIFO)"])


@router.get("/sugerir", response_model=PickingPlanResponse)
async def sugerir_picking(
    id_item: str = Query(..., description="ID del ítem a extraer"),
    cantidad: Decimal = Query(..., gt=0, description="Cantidad total requerida"),
    estrategia: str = Query("fefo", description="Estrategia: fefo, fifo, lifo"),
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
        estrategia=estrategia,
    )
