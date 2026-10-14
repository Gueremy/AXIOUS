"""Contexto efectivo de sesión para clientes v2."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies_v2 import TenantContext, get_current_tenant
from app.core.modules.registry import ModuleRegistry
from app.database import get_db
from app.services.v2.configuracion_operativa import leer_configuracion

router = APIRouter(prefix="/sesion", tags=["V2 - Sesión"])


@router.get("")
async def obtener_sesion(
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Devuelve tenant, permisos efectivos y módulos activos verificados en servidor."""
    modulos = [
        modulo.id for modulo in ModuleRegistry.get_catalog()
        if await ModuleRegistry.is_enabled(db, tenant.id_organizacion, modulo.id)
    ]
    return {
        "usuario": {"id": tenant.usuario.id, "nombre": tenant.usuario.nombre,
                    "rol": tenant.rol_codigo, "id_sede": tenant.usuario.id_sede},
        "organizacion": {"id": tenant.organizacion.id, "nombre": tenant.organizacion.nombre,
                         "slug": tenant.organizacion.slug},
        "configuracion_operativa": leer_configuracion(tenant.organizacion).model_dump(mode="json"),
        "permisos": sorted(tenant.permisos),
        "modulos_activos": modulos,
    }
