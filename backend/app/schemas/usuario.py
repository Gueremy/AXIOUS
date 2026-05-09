"""
app/schemas/usuario.py
Schemas Pydantic para el modelo Usuario.
REGLA LEY 19.628: el campo 'rut' y 'password_hash' NUNCA aparecen en ningún Read schema.
"""
import re
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, ConfigDict, field_validator
from enum import Enum


class RolEnum(str, Enum):
    super_admin  = "super_admin"
    admin_sede   = "admin_sede"
    jefe_bodega  = "jefe_bodega"
    operario     = "operario"
    gerencia     = "gerencia"


class TurnoEnum(str, Enum):
    A = "A"
    B = "B"


# ─── Lectura (respuesta de la API) ───────────────────────────────────────────
class UsuarioRead(BaseModel):
    """
    Lo que devuelve la API. Nunca incluir rut ni password_hash.
    Ley 19.628 — protección de datos personales.
    """
    model_config = ConfigDict(from_attributes=True)

    id:               str
    nombre:           str
    email:            EmailStr
    codigo_empleado:  str       # Se usa en reportes externos (no el RUT)
    rol:              RolEnum
    id_sede:          Optional[str] = None
    turno:            Optional[TurnoEnum] = None
    activo:           bool
    fecha_creacion:   datetime
    ultimo_acceso:    Optional[datetime] = None


# ─── Creación (body del POST) ─────────────────────────────────────────────────
class UsuarioCreate(BaseModel):
    nombre:          str
    email:           EmailStr
    password:        str
    codigo_empleado: str
    rol:             RolEnum
    id_sede:         Optional[str] = None
    turno:           Optional[TurnoEnum] = None

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Mínimo 8 caracteres")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Debe incluir al menos una mayúscula")
        if not re.search(r"[a-z]", v):
            raise ValueError("Debe incluir al menos una minúscula")
        if not re.search(r"\d", v):
            raise ValueError("Debe incluir al menos un número")
        if not re.search(r"[^A-Za-z0-9]", v):
            raise ValueError("Debe incluir al menos un carácter especial")
        return v


# ─── Actualización (body del PATCH) ──────────────────────────────────────────
class UsuarioUpdate(BaseModel):
    nombre:          Optional[str] = None
    email:           Optional[EmailStr] = None
    codigo_empleado: Optional[str] = None
    rol:             Optional[RolEnum] = None
    id_sede:         Optional[str] = None
    turno:           Optional[TurnoEnum] = None
    activo:          Optional[bool] = None
