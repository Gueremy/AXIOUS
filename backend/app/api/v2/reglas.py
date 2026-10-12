from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies_v2 import TenantContext, get_current_tenant
from app.database import get_db
from app.models.v2.regla_ubicacion import ReglaUbicacion
from app.schemas.v2.regla_ubicacion import (
    ReglaUbicacionCreate,
    ReglaUbicacionRead,
    ReglaUbicacionUpdate,
)

router = APIRouter(prefix="/reglas", tags=["V2 - Reglas de Ubicación"])


@router.get("/", response_model=List[ReglaUbicacionRead])
async def listar_reglas(
    tipo_regla: Optional[str] = Query(None, description="Filtrar por tipo de regla"),
    id_ubicacion: Optional[str] = Query(None, description="Filtrar por ubicación"),
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Lista las reglas de ubicación activas configuradas para la organización."""
    stmt = select(ReglaUbicacion).where(ReglaUbicacion.id_organizacion == tenant.id_organizacion)
    if tipo_regla:
        stmt = stmt.where(ReglaUbicacion.tipo_regla == tipo_regla)
    if id_ubicacion:
        stmt = stmt.where(ReglaUbicacion.id_ubicacion == id_ubicacion)

    stmt = stmt.order_by(ReglaUbicacion.codigo.asc())
    res = await db.execute(stmt)
    return res.scalars().all()


@router.post("/", response_model=ReglaUbicacionRead, status_code=status.HTTP_201_CREATED)
async def crear_regla(
    data: ReglaUbicacionCreate,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Registra una nueva regla de almacenamiento en la organización."""
    if not tenant.tiene_permiso("rbac:manage") and tenant.rol_codigo not in ("super_admin", "admin_sede"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente para configurar reglas")

    regla = ReglaUbicacion(
        id_organizacion=tenant.id_organizacion,
        codigo=data.codigo,
        nombre=data.nombre,
        tipo_regla=data.tipo_regla,
        id_sitio=data.id_sitio,
        id_zona=data.id_zona,
        id_ubicacion=data.id_ubicacion,
        configuracion=data.configuracion,
        activo=True,
    )
    db.add(regla)
    await db.commit()
    await db.refresh(regla)
    return regla


@router.patch("/{id_regla}", response_model=ReglaUbicacionRead)
async def actualizar_regla(
    id_regla: str,
    data: ReglaUbicacionUpdate,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Actualiza o desactiva una regla existente."""
    if not tenant.tiene_permiso("rbac:manage") and tenant.rol_codigo not in ("super_admin", "admin_sede"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente")

    stmt = select(ReglaUbicacion).where(
        ReglaUbicacion.id == id_regla,
        ReglaUbicacion.id_organizacion == tenant.id_organizacion,
    )
    regla = (await db.execute(stmt)).scalar_one_or_none()
    if not regla:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Regla no encontrada")

    update_dict = data.model_dump(exclude_unset=True)
    for field, val in update_dict.items():
        setattr(regla, field, val)

    await db.commit()
    await db.refresh(regla)
    return regla
