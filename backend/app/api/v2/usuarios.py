"""Administración de cuentas v2 dentro de una organización."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies_v2 import TenantContext, get_current_tenant
from app.core.audit import log_action
from app.core.security import get_password_hash
from app.database import get_db
from app.models.usuario import Usuario
from app.models.v2.rbac import Rol, UsuarioSitio
from app.models.v2.sitio import Sitio
from app.schemas.usuario import RolEnum, UsuarioCreate

router = APIRouter(prefix="/usuarios", tags=["V2 - Usuarios"])


class UsuarioV2Create(UsuarioCreate):
    id_rol_v2: Optional[str] = None
    sitios_ids: list[str] = Field(default_factory=list)


class UsuarioV2Update(BaseModel):
    nombre: Optional[str] = None
    activo: Optional[bool] = None
    rol: Optional[RolEnum] = None
    id_rol_v2: Optional[str] = None
    sitios_ids: Optional[list[str]] = None


def _exigir_admin(tenant: TenantContext) -> None:
    if not tenant.tiene_permiso("rbac:manage"):
        raise HTTPException(status_code=403, detail="Permiso insuficiente")


async def _validar_asignaciones(db: AsyncSession, tenant: TenantContext,
                                sitios_ids: list[str], id_rol_v2: Optional[str]) -> None:
    if len(sitios_ids) != len(set(sitios_ids)):
        raise HTTPException(status_code=400, detail="Sitios duplicados")
    if sitios_ids:
        ids = set((await db.execute(select(Sitio.id).where(
            Sitio.id_organizacion == tenant.id_organizacion,
            Sitio.id.in_(sitios_ids), Sitio.activo == True,
        ))).scalars().all())
        if ids != set(sitios_ids):
            raise HTTPException(status_code=404, detail="Sitio no encontrado")
    if id_rol_v2:
        role = (await db.execute(select(Rol).where(
            Rol.id == id_rol_v2, Rol.id_organizacion == tenant.id_organizacion, Rol.activo == True,
        ))).scalar_one_or_none()
        if not role:
            raise HTTPException(status_code=404, detail="Rol no encontrado")
        if role.codigo == "super_admin" and tenant.rol_codigo != "super_admin":
            raise HTTPException(status_code=403, detail="Sólo un superadministrador puede asignar ese rol")


async def _publico(db: AsyncSession, user: Usuario) -> dict:
    sitios = (await db.execute(select(UsuarioSitio.id_sitio).where(
        UsuarioSitio.id_usuario == user.id,
    ))).scalars().all()
    return {"id": user.id, "nombre": user.nombre, "email": user.email,
            "codigo_empleado": user.codigo_empleado, "rol": user.rol,
            "id_rol_v2": user.id_rol_v2, "sitios_ids": sorted(sitios), "activo": user.activo}


@router.get("")
async def listar_usuarios(tenant: TenantContext = Depends(get_current_tenant),
                          db: AsyncSession = Depends(get_db)):
    _exigir_admin(tenant)
    users = (await db.execute(select(Usuario).where(
        Usuario.id_organizacion == tenant.id_organizacion,
    ).order_by(Usuario.nombre))).scalars().all()
    return [await _publico(db, user) for user in users]


@router.post("", status_code=status.HTTP_201_CREATED)
async def crear_usuario(data: UsuarioV2Create, tenant: TenantContext = Depends(get_current_tenant),
                        db: AsyncSession = Depends(get_db)):
    _exigir_admin(tenant)
    if data.id_sede is not None:
        raise HTTPException(status_code=400, detail="La sede heredada no aplica a usuarios v2")
    if data.rol == RolEnum.super_admin and tenant.rol_codigo != "super_admin":
        raise HTTPException(status_code=403, detail="Sólo un superadministrador puede crear otro")
    await _validar_asignaciones(db, tenant, data.sitios_ids, data.id_rol_v2)
    if (await db.execute(select(Usuario.id).where(
        (Usuario.email == data.email) | (Usuario.codigo_empleado == data.codigo_empleado)
    ))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email o código de empleado ya registrado")
    user = Usuario(nombre=data.nombre, email=data.email, password_hash=get_password_hash(data.password),
                   codigo_empleado=data.codigo_empleado, rol=data.rol, turno=data.turno,
                   id_organizacion=tenant.id_organizacion, id_rol_v2=data.id_rol_v2, activo=True)
    db.add(user)
    await db.flush()
    db.add_all(UsuarioSitio(id_usuario=user.id, id_sitio=site_id) for site_id in data.sitios_ids)
    await log_action(db, tenant.usuario.id, "CREAR_USUARIO_V2", "usuario", user.id,
                     {"id_organizacion": tenant.id_organizacion, "rol": data.rol.value,
                      "sitios_ids": data.sitios_ids})
    await db.commit()
    return await _publico(db, user)


@router.patch("/{id_usuario}")
async def actualizar_usuario(id_usuario: str, data: UsuarioV2Update,
                             tenant: TenantContext = Depends(get_current_tenant),
                             db: AsyncSession = Depends(get_db)):
    _exigir_admin(tenant)
    user = (await db.execute(select(Usuario).where(
        Usuario.id == id_usuario, Usuario.id_organizacion == tenant.id_organizacion,
    ))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    changes = data.model_dump(exclude_unset=True)
    if user.id == tenant.usuario.id and (changes.get("activo") is False or "rol" in changes or "id_rol_v2" in changes):
        raise HTTPException(status_code=400, detail="No puede desactivar ni cambiar su propio rol")
    if (user.rol == "super_admin" or changes.get("rol") == RolEnum.super_admin) and tenant.rol_codigo != "super_admin":
        raise HTTPException(status_code=403, detail="Sólo un superadministrador puede gestionar ese rol")
    await _validar_asignaciones(db, tenant, changes.get("sitios_ids") or [],
                                changes.get("id_rol_v2", user.id_rol_v2))
    if "sitios_ids" in changes:
        await db.execute(UsuarioSitio.__table__.delete().where(UsuarioSitio.id_usuario == user.id))
        db.add_all(UsuarioSitio(id_usuario=user.id, id_sitio=site_id)
                   for site_id in changes.pop("sitios_ids"))
    for key, value in changes.items():
        setattr(user, key, value)
    await log_action(db, tenant.usuario.id, "ACTUALIZAR_USUARIO_V2", "usuario", user.id,
                     {"campos": sorted(data.model_fields_set), "id_organizacion": tenant.id_organizacion})
    await db.commit()
    return await _publico(db, user)
