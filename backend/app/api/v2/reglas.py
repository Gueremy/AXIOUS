from typing import List, Optional
from decimal import Decimal, InvalidOperation
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies_v2 import TenantContext, get_current_tenant
from app.core.audit import log_action
from app.core.site_access import allowed_location_ids, require_location_access, require_zone_access
from app.database import get_db
from app.models.v2.regla_ubicacion import ReglaUbicacion
from app.models.v2.sitio import Sitio
from app.models.v2.zona import Zona
from app.schemas.v2.regla_ubicacion import (
    ReglaUbicacionCreate,
    ReglaUbicacionRead,
    ReglaUbicacionUpdate,
)

router = APIRouter(prefix="/reglas", tags=["V2 - Reglas de Ubicación"])


def _validar_configuracion(tipo: str, config: dict) -> None:
    if tipo == "capacidad":
        for campo in ("maximo", "umbral_porcentaje"):
            if campo not in config:
                continue
            try:
                valor = Decimal(str(config[campo]))
            except (InvalidOperation, ValueError, TypeError):
                raise HTTPException(status_code=422, detail=f"{campo} debe ser numérico")
            if not valor.is_finite() or valor < 0 or (campo == "umbral_porcentaje" and valor > 100):
                raise HTTPException(status_code=422, detail=f"{campo} fuera de rango")
    elif tipo in ("items_permitidos", "categorias_permitidas"):
        campo = "items" if tipo == "items_permitidos" else "categorias"
        if campo in config and (not isinstance(config[campo], list) or
                                not all(isinstance(x, str) for x in config[campo])):
            raise HTTPException(status_code=422, detail=f"{campo} debe ser una lista de códigos")
    elif tipo == "mezcla_lotes" and "permite_mezcla" in config:
        if not isinstance(config["permite_mezcla"], bool):
            raise HTTPException(status_code=422, detail="permite_mezcla debe ser booleano")


def _scope_reglas(stmt, tenant: TenantContext):
    if tenant.sitios_permitidos is None:
        return stmt
    return stmt.where(or_(
        ReglaUbicacion.id_sitio.in_(tenant.sitios_permitidos),
        ReglaUbicacion.id_zona.in_(select(Zona.id).where(
            Zona.id_organizacion == tenant.id_organizacion,
            Zona.id_sitio.in_(tenant.sitios_permitidos))),
        ReglaUbicacion.id_ubicacion.in_(allowed_location_ids(tenant)),
        (ReglaUbicacion.id_sitio.is_(None) & ReglaUbicacion.id_zona.is_(None)
         & ReglaUbicacion.id_ubicacion.is_(None)),
    ))


async def _validar_alcance_regla(db: AsyncSession, tenant: TenantContext,
                                id_sitio: Optional[str], id_zona: Optional[str],
                                id_ubicacion: Optional[str]) -> None:
    sites = set()
    if id_sitio:
        exists = (await db.execute(select(Sitio.id).where(
            Sitio.id == id_sitio, Sitio.id_organizacion == tenant.id_organizacion,
        ))).scalar_one_or_none()
        if not exists:
            raise HTTPException(status_code=404, detail="Sitio no encontrado")
        sites.add(exists)
    if id_zona:
        sites.add(await require_zone_access(db, tenant, id_zona))
    if id_ubicacion:
        sites.add(await require_location_access(db, tenant, id_ubicacion))
    if len(sites) > 1:
        raise HTTPException(status_code=400, detail="La regla apunta a sitios diferentes")
    if tenant.sitios_permitidos is not None and not sites:
        raise HTTPException(status_code=403, detail="La regla global requiere acceso a toda la organización")
    for site_id in sites:
        tenant.exigir_acceso_sitio(site_id)


@router.get("/", response_model=List[ReglaUbicacionRead])
async def listar_reglas(
    tipo_regla: Optional[str] = Query(None, description="Filtrar por tipo de regla"),
    id_ubicacion: Optional[str] = Query(None, description="Filtrar por ubicación"),
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Lista las reglas de ubicación activas configuradas para la organización."""
    stmt = _scope_reglas(select(ReglaUbicacion).where(
        ReglaUbicacion.id_organizacion == tenant.id_organizacion), tenant)
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
    await _validar_alcance_regla(db, tenant, data.id_sitio, data.id_zona, data.id_ubicacion)
    _validar_configuracion(data.tipo_regla, data.configuracion)

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
    await db.flush()
    await log_action(db, tenant.usuario.id, "CREAR_REGLA_UBICACION_V2", "v2_regla_ubicacion",
                     regla.id, {"id_organizacion": tenant.id_organizacion, "codigo": regla.codigo})
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

    await _validar_alcance_regla(db, tenant, regla.id_sitio, regla.id_zona, regla.id_ubicacion)

    update_dict = data.model_dump(exclude_unset=True)
    await _validar_alcance_regla(db, tenant,
                                update_dict.get("id_sitio", regla.id_sitio),
                                update_dict.get("id_zona", regla.id_zona),
                                update_dict.get("id_ubicacion", regla.id_ubicacion))
    if "configuracion" in update_dict and update_dict["configuracion"] is not None:
        _validar_configuracion(update_dict.get("tipo_regla", regla.tipo_regla), update_dict["configuracion"])
    for field, val in update_dict.items():
        setattr(regla, field, val)

    await log_action(db, tenant.usuario.id, "ACTUALIZAR_REGLA_UBICACION_V2", "v2_regla_ubicacion",
                     regla.id, {"id_organizacion": tenant.id_organizacion,
                                "campos": sorted(update_dict)})

    await db.commit()
    await db.refresh(regla)
    return regla
