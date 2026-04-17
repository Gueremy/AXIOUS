"""
app/core/dependencies.py
Dependencias FastAPI reutilizables en todos los routers.
Aplicar con: Depends(get_current_user) o Depends(require_role(["admin"]))
"""
from typing import List

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_token
from app.database import get_db
from app.models.usuario import Usuario

# Apunta al endpoint de login — Swagger usa esto para el botón "Authorize"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ─── Usuario actual ───────────────────────────────────────────────────────────
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> Usuario:
    """
    Extrae el JWT del header Authorization: Bearer <token>,
    lo valida y devuelve el objeto Usuario de la BD.
    Si el token es inválido, expirado o el usuario no existe → 401.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudo validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = verify_token(token, expected_type="access")
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await db.execute(select(Usuario).where(Usuario.id == user_id))
    usuario = result.scalar_one_or_none()

    if usuario is None:
        raise credentials_exception
    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario desactivado. Contacte al administrador.",
        )
    return usuario


# ─── Guard por rol ────────────────────────────────────────────────────────────
def require_role(roles: List[str]):
    """
    Factory de dependencias. Verifica que el usuario autenticado
    tenga uno de los roles permitidos.

    Uso:
        @router.get("/ruta")
        async def mi_endpoint(user = Depends(require_role(["super_admin", "jefe_bodega"]))):
            ...
    """
    async def _check_role(
        current_user: Usuario = Depends(get_current_user),
    ) -> Usuario:
        if current_user.rol not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"No tienes permiso para esta acción. "
                       f"Roles permitidos: {', '.join(roles)}",
            )
        return current_user

    return _check_role


# ─── Usuario opcional (endpoints semi-públicos) ───────────────────────────────
async def get_optional_user(
    token: str = Depends(OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)),
    db: AsyncSession = Depends(get_db),
) -> Usuario | None:
    """
    Igual que get_current_user pero no lanza error si no hay token.
    Útil para endpoints que se comportan diferente con o sin sesión.
    """
    if not token:
        return None
    try:
        payload = verify_token(token, expected_type="access")
        user_id: str = payload.get("sub")
        if not user_id:
            return None
        result = await db.execute(select(Usuario).where(Usuario.id == user_id))
        return result.scalar_one_or_none()
    except JWTError:
        return None
