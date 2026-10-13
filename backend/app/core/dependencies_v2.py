"""
app/core/dependencies_v2.py
Resolución central del tenant y control de acceso basado en roles y permisos (RBAC v2).
Garantiza aislamiento estricto por organización, validación de estado activo y restricciones de sitio.
"""
from dataclasses import dataclass
from typing import List, Optional, Set
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import verify_token
from app.database import get_db
from app.models.usuario import Usuario
from app.models.v2.organizacion import Organizacion
from app.models.v2.rbac import Rol, Permiso, UsuarioSitio

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# Plantillas de permisos por defecto para los roles iniciales del sistema
PLANTILLAS_PERMISOS = {
    "super_admin": {
        "sitio:read", "sitio:write", "sitio:delete",
        "zona:read", "zona:write", "zona:delete",
        "ubicacion:read", "ubicacion:write", "ubicacion:delete",
        "item:read", "item:write", "item:delete",
        "lote:read", "lote:write",
        "stock:read", "stock:adjust",
        "movimiento:create", "movimiento:approve", "movimiento:reject",
        "esquema:write", "esquema:read",
        "rbac:manage", "dashboard:read", "reporte:export",
    },
    "admin_sede": {
        "sitio:read", "sitio:write",
        "zona:read", "zona:write",
        "ubicacion:read", "ubicacion:write",
        "item:read", "item:write",
        "lote:read", "lote:write",
        "stock:read",
        "movimiento:create", "movimiento:approve", "movimiento:reject",
        "esquema:read", "dashboard:read", "reporte:export",
    },
    "jefe_bodega": {
        "sitio:read", "zona:read", "ubicacion:read",
        "item:read", "lote:read", "stock:read",
        "movimiento:create", "movimiento:approve", "movimiento:reject",
        "dashboard:read", "reporte:export",
    },
    "operario": {
        "sitio:read", "zona:read", "ubicacion:read",
        "item:read", "lote:read", "stock:read",
        "movimiento:create",
    },
    "gerencia": {
        "sitio:read", "zona:read", "ubicacion:read",
        "item:read", "lote:read", "stock:read",
        "dashboard:read", "reporte:export",
    },
}


@dataclass
class TenantContext:
    usuario: Usuario
    organizacion: Organizacion
    rol_codigo: str
    permisos: Set[str]
    sitios_permitidos: Optional[Set[str]]  # None = sin restricción de sitios (acceso a toda la org)

    @property
    def id_organizacion(self) -> str:
        return self.organizacion.id

    def tiene_permiso(self, permiso: str) -> bool:
        if self.rol_codigo == "super_admin":
            return True
        return permiso in self.permisos

    def validar_pertenencia_org(self, id_org_recurso: str) -> None:
        """
        Lanza 404 si el recurso pertenece a otra organización.
        Se usa 404 para evitar inferencia de existencia de datos de otros tenants.
        """
        if id_org_recurso != self.id_organizacion:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Recurso no encontrado",
            )

    def puede_acceder_sitio(self, id_sitio: str) -> bool:
        """Verifica si el usuario tiene permiso para operar en el sitio dado."""
        if self.rol_codigo in ("super_admin", "gerencia"):
            return True
        if self.sitios_permitidos is None:
            return True
        return id_sitio in self.sitios_permitidos

    def exigir_acceso_sitio(self, id_sitio: str) -> None:
        if not self.puede_acceder_sitio(id_sitio):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tiene acceso a este sitio")


async def get_current_tenant(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> TenantContext:
    """
    Dependencia central que valida usuario activo, organización activa y resuelve
    los permisos del usuario dentro de su organización.
    """
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales inválidas o expiradas",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = verify_token(token, expected_type="access")
        user_id: str = payload.get("sub")
        if not user_id:
            raise credentials_exc
    except JWTError:
        raise credentials_exc

    # 1. Cargar usuario
    stmt_user = select(Usuario).where(Usuario.id == user_id)
    res_user = await db.execute(stmt_user)
    usuario = res_user.scalar_one_or_none()

    if not usuario:
        raise credentials_exc
    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cuenta de usuario desactivada.",
        )

    # 2. La pertenencia persistida prevalece; un claim obsoleto nunca cambia el tenant.
    id_org = usuario.id_organizacion
    if payload.get("org_id") and payload["org_id"] != id_org:
        raise credentials_exc
    if not id_org:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El usuario no pertenece a ninguna organización.",
        )

    stmt_org = select(Organizacion).where(Organizacion.id == id_org)
    res_org = await db.execute(stmt_org)
    organizacion = res_org.scalar_one_or_none()

    if not organizacion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organización no encontrada.",
        )
    if not organizacion.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La organización se encuentra desactivada.",
        )

    # 3. Determinar rol y permisos
    rol_codigo = usuario.rol or "operario"
    permisos = set()

    # Si tiene un rol v2 personalizado asignado, cargarlo
    if usuario.id_rol_v2:
        stmt_rol = select(Rol).where(Rol.id == usuario.id_rol_v2).options(selectinload(Rol.permisos))
        res_rol = await db.execute(stmt_rol)
        rol_obj = res_rol.scalar_one_or_none()
        if not rol_obj or not rol_obj.activo or rol_obj.id_organizacion != id_org:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Rol no disponible para esta organización")
        rol_codigo = rol_obj.codigo
        permisos = {p.codigo for p in rol_obj.permisos}

    # Si no tiene permisos asignados explícitos, usar plantilla base del rol
    if not usuario.id_rol_v2 and rol_codigo in PLANTILLAS_PERMISOS:
        permisos = set(PLANTILLAS_PERMISOS[rol_codigo])

    # 4. Determinar restricciones de sitio
    stmt_sitios = select(UsuarioSitio.id_sitio).where(UsuarioSitio.id_usuario == usuario.id)
    res_sitios = await db.execute(stmt_sitios)
    sitios_asignados = set(res_sitios.scalars().all())
    sitios_permitidos = None if rol_codigo in ("super_admin", "gerencia") else sitios_asignados

    return TenantContext(
        usuario=usuario,
        organizacion=organizacion,
        rol_codigo=rol_codigo,
        permisos=permisos,
        sitios_permitidos=sitios_permitidos,
    )


def require_permission(permiso: str):
    """Factory de dependencias para validar permisos en endpoints v2."""
    async def _permiso_checker(tenant: TenantContext = Depends(get_current_tenant)) -> TenantContext:
        if not tenant.tiene_permiso(permiso):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permiso insuficiente para esta operación. Requerido: {permiso}",
            )
        return tenant
    return _permiso_checker
