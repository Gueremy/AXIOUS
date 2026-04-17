"""
app/core/security.py
Funciones de hashing, JWT y verificación de credenciales.
NUNCA usar ALGORITHM distinto a HS256 — CVE-2024-33663 en python-jose con ECDSA.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# ─── Bcrypt — cost factor mínimo 12 ──────────────────────────────────────────
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
)

# ─── Constante de algoritmo — NO parametrizable ───────────────────────────────
ALGORITHM = "HS256"


# ─── Password ─────────────────────────────────────────────────────────────────
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Compara contraseña en texto plano con el hash bcrypt almacenado."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Genera hash bcrypt con cost=12. Usar siempre antes de guardar en BD."""
    return pwd_context.hash(password)


# ─── JWT ──────────────────────────────────────────────────────────────────────
def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Genera un JWT de acceso firmado con HS256.
    - Expiración por defecto: ACCESS_TOKEN_EXPIRE_MINUTES del .env
    - El campo 'sub' debe ser el id (UUID) del usuario.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta
        if expires_delta
        else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict) -> str:
    """
    Genera un JWT de refresco firmado con HS256.
    - Expiración: REFRESH_TOKEN_EXPIRE_DAYS del .env (por defecto 7 días)
    - Solo sirve para obtener un nuevo access_token.
    """
    import uuid
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    to_encode.update({
        "exp": expire, 
        "type": "refresh",
        "jti": str(uuid.uuid4())
    })
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str, expected_type: str = "access") -> dict:
    """
    Decodifica y valida un JWT.
    - Verifica firma, expiración y tipo (access vs refresh).
    - Lanza JWTError si el token es inválido o expirado.
    - El caller debe atrapar JWTError y devolver 401.
    """
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    if payload.get("type") != expected_type:
        raise JWTError("Tipo de token incorrecto")
    return payload
