"""Roles y permisos configurables para cada organización."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.audit import log_action
from app.core.dependencies_v2 import PLANTILLAS_PERMISOS, TenantContext, get_current_tenant
from app.database import get_db
from app.models.v2.rbac import Permiso, Rol

router = APIRouter(prefix="/roles", tags=["V2 - Roles y permisos"])
KNOWN_PERMISSIONS = sorted(set().union(*PLANTILLAS_PERMISOS.values()))
RESERVED_ROLES = set(PLANTILLAS_PERMISOS)


class RolCreate(BaseModel):
    codigo: str = Field(..., pattern=r"^[a-z][a-z0-9_]{2,49}$")
    nombre: str = Field(..., min_length=2, max_length=100)
    descripcion: Optional[str] = Field(None, max_length=250)
    permisos: list[str] = Field(default_factory=list)


class RolUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=2, max_length=100)
    descripcion: Optional[str] = Field(None, max_length=250)
    activo: Optional[bool] = None
    permisos: Optional[list[str]] = None


def _exigir_admin(tenant: TenantContext) -> None:
    if not tenant.tiene_permiso("rbac:manage"):
        raise HTTPException(status_code=403, detail="Permiso insuficiente")


async def _asignar_permisos(db: AsyncSession, role: Rol, codes: list[str]) -> None:
    unknown = set(codes) - set(KNOWN_PERMISSIONS)
    if unknown:
        raise HTTPException(status_code=400, detail=f"Permisos desconocidos: {', '.join(sorted(unknown))}")
    stored = (await db.execute(select(Permiso).where(Permiso.codigo.in_(codes)))).scalars().all()
    by_code = {permission.codigo: permission for permission in stored}
    for code in codes:
        if code not in by_code:
            permission = Permiso(codigo=code, modulo=code.split(":")[0], descripcion=code)
            db.add(permission)
            by_code[code] = permission
    role.permisos = [by_code[code] for code in sorted(set(codes))]


def _publico(role: Rol) -> dict:
    return {"id": role.id, "codigo": role.codigo, "nombre": role.nombre,
            "descripcion": role.descripcion, "activo": role.activo,
            "es_sistema": role.es_sistema, "permisos": sorted(p.codigo for p in role.permisos)}


@router.get("/permisos")
async def listar_permisos(tenant: TenantContext = Depends(get_current_tenant)):
    _exigir_admin(tenant)
    return KNOWN_PERMISSIONS


@router.get("")
async def listar_roles(tenant: TenantContext = Depends(get_current_tenant),
                       db: AsyncSession = Depends(get_db)):
    _exigir_admin(tenant)
    roles = (await db.execute(select(Rol).where(Rol.id_organizacion == tenant.id_organizacion)
                              .options(selectinload(Rol.permisos)).order_by(Rol.codigo))).scalars().all()
    return [_publico(role) for role in roles]


@router.post("/plantillas")
async def cargar_plantillas(tenant: TenantContext = Depends(get_current_tenant),
                            db: AsyncSession = Depends(get_db)):
    _exigir_admin(tenant)
    existing = (await db.execute(select(Rol.codigo).where(
        Rol.id_organizacion == tenant.id_organizacion,
    ))).scalars().all()
    created = []
    for code, codes in PLANTILLAS_PERMISOS.items():
        if code in existing:
            continue
        role = Rol(id_organizacion=tenant.id_organizacion, codigo=code,
                   nombre=code.replace("_", " ").title(), activo=True, es_sistema=True,
                   permisos=[])
        db.add(role)
        await _asignar_permisos(db, role, sorted(codes))
        created.append(code)
    if created:
        await log_action(db, tenant.usuario.id, "CARGAR_PLANTILLAS_ROLES_V2", "v2_rol",
                         tenant.id_organizacion, {"roles": created})
    await db.commit()
    return {"creadas": created}


@router.post("", status_code=201)
async def crear_rol(data: RolCreate, tenant: TenantContext = Depends(get_current_tenant),
                    db: AsyncSession = Depends(get_db)):
    _exigir_admin(tenant)
    if data.codigo in RESERVED_ROLES:
        raise HTTPException(status_code=400, detail="Código reservado para plantilla del sistema")
    if (await db.execute(select(Rol.id).where(Rol.id_organizacion == tenant.id_organizacion,
                                            Rol.codigo == data.codigo))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="El rol ya existe")
    role = Rol(id_organizacion=tenant.id_organizacion, codigo=data.codigo, nombre=data.nombre,
               descripcion=data.descripcion, activo=True, es_sistema=False, permisos=[])
    db.add(role)
    await _asignar_permisos(db, role, data.permisos)
    await db.flush()
    await log_action(db, tenant.usuario.id, "CREAR_ROL_V2", "v2_rol", role.id,
                     {"id_organizacion": tenant.id_organizacion, "codigo": role.codigo,
                      "permisos": sorted(data.permisos)})
    await db.commit()
    return _publico(role)


@router.patch("/{id_rol}")
async def actualizar_rol(id_rol: str, data: RolUpdate,
                         tenant: TenantContext = Depends(get_current_tenant),
                         db: AsyncSession = Depends(get_db)):
    _exigir_admin(tenant)
    role = (await db.execute(select(Rol).where(
        Rol.id == id_rol, Rol.id_organizacion == tenant.id_organizacion,
    ).options(selectinload(Rol.permisos)))).scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Rol no encontrado")
    if role.es_sistema:
        raise HTTPException(status_code=403, detail="La plantilla del sistema no se puede editar")
    if data.nombre is not None:
        role.nombre = data.nombre
    if "descripcion" in data.model_fields_set:
        role.descripcion = data.descripcion
    if data.activo is not None:
        role.activo = data.activo
    if data.permisos is not None:
        await _asignar_permisos(db, role, data.permisos)
    await log_action(db, tenant.usuario.id, "ACTUALIZAR_ROL_V2", "v2_rol", role.id,
                     {"id_organizacion": tenant.id_organizacion, "campos": sorted(data.model_fields_set)})
    await db.commit()
    return _publico(role)
