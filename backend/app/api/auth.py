"""
app/api/auth.py
Endpoints de autenticación JWT.

Flujo de login:
  1. Buscar usuario por email
  2. Si no existe → 401 (mismo mensaje que contraseña incorrecta → evitar enumeración)
  3. Verificar bcrypt
  4. Verificar usuario.activo
  5. Actualizar ultimo_acceso
  6. Guardar refresh_token en BD (Opción B — revocación real)
  7. Devolver access_token + refresh_token

Rate limiting: 5 intentos / 5 minutos por IP en /auth/login
"""
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_current_user, require_role
from app.core.security import (
    create_access_token,
    create_refresh_token,
    get_password_hash,
    verify_password,
    verify_token,
)
from app.database import get_db
from app.models.refresh_token import RefreshToken
from app.models.usuario import Usuario
from app.schemas.auth import RefreshRequest, TokenResponse, ForgotPasswordRequest, ResetPasswordRequest
from app.schemas.usuario import UsuarioCreate, UsuarioRead

router = APIRouter()


# ─── Helpers privados ─────────────────────────────────────────────────────────
async def _save_refresh_token(
    db: AsyncSession, token_str: str, id_usuario: str
) -> None:
    """Persiste el refresh token en BD para permitir revocación real."""
    expiry = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    db.add(
        RefreshToken(
            id=str(uuid.uuid4()),
            token=token_str,
            id_usuario=id_usuario,
            revocado=False,
            fecha_expiracion=expiry,
        )
    )
    await db.commit()


# ─── POST /auth/login ─────────────────────────────────────────────────────────
@router.post("/login", response_model=TokenResponse, summary="Iniciar sesión")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """
    Autentica con email + password (vía form-data estándar de OAuth2).
    El campo 'username' del formulario corresponde al email.
    Devuelve access_token (60 min) y refresh_token (7 días, guardado en BD).

    Rate limit: 5 intentos por IP cada 5 minutos.
    """
    # 1. Buscar usuario por email (Swagger mapea email en form_data.username)
    result = await db.execute(
        select(Usuario).where(Usuario.email == form_data.username)
    )
    usuario = result.scalar_one_or_none()

    # 2 & 3. Mensaje idéntico para usuario inexistente o contraseña incorrecta
    INVALID_MSG = "Credenciales inválidas"
    
    if usuario is not None:
        if usuario.bloqueo_hasta and usuario.bloqueo_hasta > datetime.now(timezone.utc):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cuenta bloqueada por demasiados intentos. Intente en 15 minutos.")
            
        if not verify_password(form_data.password, usuario.password_hash):
            usuario.intentos_fallidos = (usuario.intentos_fallidos or 0) + 1
            if usuario.intentos_fallidos >= 5:
                usuario.bloqueo_hasta = datetime.now(timezone.utc) + timedelta(minutes=15)
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=INVALID_MSG,
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        # Reseteo de fallos si login exitoso
        usuario.intentos_fallidos = 0
        usuario.bloqueo_hasta = None
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_MSG,
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 4. Verificar que el usuario esté activo
    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuario desactivado. Contacte al administrador.",
        )

    # 5. Actualizar ultimo_acceso
    usuario.ultimo_acceso = datetime.now(timezone.utc)

    # 6. Generar tokens
    token_data = {"sub": usuario.id, "rol": usuario.rol}
    access_token  = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    # 7. Persistir refresh token en BD (Opción B)
    await _save_refresh_token(db, refresh_token, usuario.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


# ─── POST /auth/refresh ───────────────────────────────────────────────────────
@router.post("/refresh", response_model=TokenResponse, summary="Refrescar token")
async def refresh(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Recibe un refresh_token válido y no revocado.
    Devuelve un nuevo par de tokens y revoca el anterior (rotación).
    """
    # Validar JWT
    try:
        payload = verify_token(body.refresh_token, expected_type="refresh")
        user_id: str = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Refresh token inválido o expirado")

    # Verificar en BD que no esté revocado
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token == body.refresh_token,
            RefreshToken.revocado == False,  # noqa: E712
        )
    )
    stored = result.scalar_one_or_none()
    if not stored:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Refresh token revocado o inexistente")

    # Verificar usuario activo
    result = await db.execute(select(Usuario).where(Usuario.id == user_id))
    usuario = result.scalar_one_or_none()
    if not usuario or not usuario.activo:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Usuario no encontrado o desactivado")

    # Revocar token anterior (rotación de tokens)
    stored.revocado = True

    # Generar nuevos tokens
    token_data = {"sub": usuario.id, "rol": usuario.rol}
    new_access  = create_access_token(token_data)
    new_refresh = create_refresh_token(token_data)
    await _save_refresh_token(db, new_refresh, usuario.id)

    return TokenResponse(access_token=new_access, refresh_token=new_refresh)


# ─── GET /auth/me ─────────────────────────────────────────────────────────────
@router.get("/me", response_model=UsuarioRead, summary="Mi perfil")
async def me(current_user: Usuario = Depends(get_current_user)):
    """
    Devuelve el perfil del usuario autenticado.
    Nunca incluye rut ni password_hash (Ley 19.628).
    """
    return current_user


# ─── POST /auth/logout ────────────────────────────────────────────────────────
@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Cerrar sesión")
async def logout(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """
    Revoca el refresh token en BD.
    El access_token sigue válido hasta su expiración (60 min) — comportamiento estándar JWT.
    """
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token == body.refresh_token,
            RefreshToken.id_usuario == current_user.id,
        )
    )
    stored = result.scalar_one_or_none()
    if stored:
        stored.revocado = True
        await db.commit()


# ─── POST /auth/register ──────────────────────────────────────────────────────
@router.post(
    "/register",
    response_model=UsuarioRead,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar usuario (solo Super Admin)",
)
async def register(
    body: UsuarioCreate,
    db: AsyncSession = Depends(get_db),
    _: Usuario = Depends(require_role(["super_admin"])),
):
    """
    Crea un nuevo usuario. Solo accesible para el rol super_admin.
    La contraseña se hashea con bcrypt cost=12 antes de guardarla.
    """
    # Verificar email único
    existing = await db.execute(
        select(Usuario).where(Usuario.email == body.email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un usuario con ese email",
        )

    # Verificar codigo_empleado único
    existing_code = await db.execute(
        select(Usuario).where(Usuario.codigo_empleado == body.codigo_empleado)
    )
    if existing_code.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un usuario con ese código de empleado",
        )

    nuevo = Usuario(
        id=str(uuid.uuid4()),
        nombre=body.nombre,
        email=body.email,
        password_hash=get_password_hash(body.password),
        codigo_empleado=body.codigo_empleado,
        rol=body.rol,
        id_sede=body.id_sede,
        turno=body.turno,
        activo=True,
    )
    db.add(nuevo)
    await db.commit()
    await db.refresh(nuevo)
    return nuevo


# ─── POST /auth/forgot-password ───────────────────────────────────────────────
@router.post("/forgot-password", summary="Solicitar recuperación de clave")
async def forgot_password(
    body: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Simula el envío de un correo electrónico con un token de recuperación.
    Siempre devuelve 200 OK para evitar la enumeración de emails.
    """
    result = await db.execute(select(Usuario).where(Usuario.email == body.email))
    usuario = result.scalar_one_or_none()
    
    if usuario:
        token = str(uuid.uuid4())
        usuario.reset_token = token
        usuario.reset_token_expire = datetime.now(timezone.utc) + timedelta(hours=1)
        await db.commit()
        # TODO: Integración SMTP a futuro. Print simulado:
        # print(f"Email to {usuario.email}: token={token}")

    return {"mensaje": "Si el correo existe en nuestro sistema, recibirá un enlace de recuperación."}


# ─── POST /auth/reset-password ────────────────────────────────────────────────
@router.post("/reset-password", summary="Restablecer contraseña con token")
async def reset_password(
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Recibe el token de recuperación y una nueva contraseña.
    Restablece la cuenta y sus bloqueos anteriores.
    """
    result = await db.execute(
        select(Usuario).where(
            Usuario.reset_token == body.token,
            Usuario.reset_token_expire > datetime.now(timezone.utc)
        )
    )
    usuario = result.scalar_one_or_none()
    
    if not usuario:
        raise HTTPException(status_code=400, detail="Token inválido o expirado")
        
    usuario.password_hash = get_password_hash(body.new_password)
    usuario.reset_token = None
    usuario.reset_token_expire = None
    usuario.intentos_fallidos = 0
    usuario.bloqueo_hasta = None
    
    await db.commit()
    return {"mensaje": "Contraseña actualizada exitosamente, ya puede iniciar sesión."}
