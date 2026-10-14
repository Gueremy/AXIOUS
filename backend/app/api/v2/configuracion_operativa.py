from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_action
from app.core.dependencies_v2 import TenantContext, get_current_tenant
from app.database import get_db
from app.models.v2.organizacion import Organizacion
from app.services.v2.configuracion_operativa import (
    ConfiguracionOperativa, UmbralesColor, UnidadConfig, UNIDADES_BASE, leer_configuracion,
)

router = APIRouter(prefix="/configuracion-operativa", tags=["V2 - Configuración operativa"])


class ConfiguracionOperativaUpdate(BaseModel):
    umbrales_color: UmbralesColor | None = None
    paleta_colores: dict[str, str] | None = None
    unidades: dict[str, UnidadConfig] | None = None


@router.get("", response_model=ConfiguracionOperativa)
async def consultar_configuracion(
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    if not tenant.tiene_permiso("dashboard:read"):
        raise HTTPException(status_code=403, detail="Permiso insuficiente")
    org = (await db.execute(select(Organizacion).where(
        Organizacion.id == tenant.id_organizacion,
    ))).scalar_one()
    return leer_configuracion(org)


@router.patch("", response_model=ConfiguracionOperativa)
async def actualizar_configuracion(
    data: ConfiguracionOperativaUpdate,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    if not tenant.tiene_permiso("rbac:manage"):
        raise HTTPException(status_code=403, detail="Permiso insuficiente")
    org = (await db.execute(select(Organizacion).where(
        Organizacion.id == tenant.id_organizacion,
    ).with_for_update())).scalar_one()
    actual = dict(org.configuracion or {})
    operativa = dict(actual.get("operativa", {}))
    if data.umbrales_color is not None:
        operativa["umbrales_color"] = data.umbrales_color.model_dump()
    if data.paleta_colores is not None:
        import re
        if any(not re.fullmatch(r"#[0-9A-Fa-f]{6}", color)
               for color in data.paleta_colores.values()):
            raise HTTPException(status_code=422, detail="Cada color debe tener formato hexadecimal #RRGGBB")
        if any(key not in ("libre", "optima", "alerta", "critica", "retenido")
               for key in data.paleta_colores):
            raise HTTPException(status_code=422, detail="Estado de color desconocido")
        operativa["paleta_colores"] = {
            **operativa.get("paleta_colores", {}), **data.paleta_colores,
        }
    if data.unidades is not None:
        if any(not codigo or len(codigo) > 20 for codigo in data.unidades):
            raise HTTPException(status_code=422, detail="Código de unidad inválido")
        if any(codigo in UNIDADES_BASE and unidad != UNIDADES_BASE[codigo]
               for codigo, unidad in data.unidades.items()):
            raise HTTPException(status_code=422, detail="Los factores de las unidades estándar son fijos")
        unidades = dict(operativa.get("unidades", {}))
        unidades.update({codigo: unidad.model_dump(mode="json")
                        for codigo, unidad in data.unidades.items()})
        operativa["unidades"] = unidades
    actual["operativa"] = operativa
    org.configuracion = actual
    await log_action(db, tenant.usuario.id, "ACTUALIZAR_CONFIGURACION_OPERATIVA_V2",
                     "v2_organizacion", org.id, {"campos": sorted(data.model_fields_set)})
    await db.commit()
    await db.refresh(org)
    return leer_configuracion(org)
