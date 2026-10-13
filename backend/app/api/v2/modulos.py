from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies_v2 import TenantContext, get_current_tenant
from app.core.audit import log_action
from app.core.modules.registry import ModuleRegistry, MODULOS_CATALOGO
from app.database import get_db
from app.schemas.v2.modulo import ModuloEstadoUpdate, ModuloItemRead

router = APIRouter(prefix="/modulos", tags=["V2 - Módulos y Feature Flags"])


@router.get("", response_model=List[ModuloItemRead])
async def listar_modulos(
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Retorna el catálogo completo de módulos y su estado de activación para la organización."""
    resultado = []
    for m in ModuleRegistry.get_catalog():
        is_active = await ModuleRegistry.is_enabled(db, tenant.id_organizacion, m.id)
        resultado.append(
            ModuloItemRead(
                id=m.id,
                nombre=m.nombre,
                version=m.version,
                descripcion=m.descripcion,
                habilitado=is_active,
                rutas_api=m.rutas_api,
                configuracion={},
            )
        )
    return resultado


@router.patch("/{id_modulo}", response_model=ModuloItemRead)
async def actualizar_estado_modulo(
    id_modulo: str,
    payload: ModuloEstadoUpdate,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Activa o desactiva una capacidad/módulo para la organización autenticada."""
    if not tenant.tiene_permiso("rbac:manage"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente para administrar módulos")

    if id_modulo not in MODULOS_CATALOGO:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Módulo no encontrado en el catálogo")

    await log_action(db, tenant.usuario.id, "CONFIGURAR_MODULO_V2", "v2_organizacion_modulo",
                     id_modulo, {"id_organizacion": tenant.id_organizacion,
                                 "habilitado": payload.habilitado})

    mod_org = await ModuleRegistry.set_module_status(
        db=db,
        id_organizacion=tenant.id_organizacion,
        id_modulo=id_modulo,
        habilitado=payload.habilitado,
        configuracion=payload.configuracion,
    )

    manifest = MODULOS_CATALOGO[id_modulo]
    return ModuloItemRead(
        id=manifest.id,
        nombre=manifest.nombre,
        version=manifest.version,
        descripcion=manifest.descripcion,
        habilitado=mod_org.habilitado,
        rutas_api=manifest.rutas_api,
        configuracion=mod_org.configuracion or {},
    )
