from typing import Any, Dict
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies_v2 import TenantContext, get_current_tenant
from app.database import get_db
from app.services.v2.demo_service import DemoGeneratorService

router = APIRouter(prefix="/demo", tags=["V2 - Generador de Datos Demo"])


@router.post("/seed", status_code=status.HTTP_201_CREATED)
async def sembrar_datos_demo(
    preset: str = Query("salmonera", description="Preset: salmonera o general"),
    en_organizacion_actual: bool = Query(True, description="Si es True, puebla la organización actual; si es False, crea una nueva."),
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Puebla un dataset ficticio reproducible para demostraciones y pruebas del sistema.
    """
    org_id = tenant.id_organizacion if en_organizacion_actual else None
    return await DemoGeneratorService.generar_demo(db, preset=preset, id_organizacion_existente=org_id)
