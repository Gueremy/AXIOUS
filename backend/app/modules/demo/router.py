from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies_v2 import TenantContext, get_current_tenant
from app.core.modules.registry import require_module_enabled
from app.core.config import settings
from app.database import get_db
from app.modules.demo.service import DemoGeneratorService

router = APIRouter(prefix="/demo", tags=["V2 - Generador de Datos Demo"],
                   dependencies=[Depends(require_module_enabled("demo"))])


@router.post("/seed", status_code=status.HTTP_201_CREATED)
async def sembrar_datos_demo(
    preset: str = Query("salmonera", description="Preset: salmonera, general, retail o portuario"),
    en_organizacion_actual: bool = Query(True, description="Si es True, puebla la organización actual; si es False, crea una nueva."),
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Puebla un dataset ficticio reproducible para demostraciones y pruebas del sistema.
    """
    if not tenant.tiene_permiso("rbac:manage"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente para generar datos demo")
    if not en_organizacion_actual and settings.ENVIRONMENT == "production":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Creación de organizaciones demo deshabilitada")
    org_id = tenant.id_organizacion if en_organizacion_actual else None
    return await DemoGeneratorService.generar_demo(db, preset=preset, id_organizacion_existente=org_id,
                                                   id_usuario_demo=tenant.usuario.id if org_id else None)
