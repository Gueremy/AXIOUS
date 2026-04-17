"""
app/schemas/usuario.py
Schemas Pydantic para el modelo Usuario.
REGLA LEY 19.628: el campo 'rut' y 'password_hash' NUNCA aparecen en ningún Read schema.
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, ConfigDict
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
    password:        str        # Se hashea en el router, nunca se almacena en texto plano
    codigo_empleado: str
    rol:             RolEnum
    id_sede:         Optional[str] = None
    turno:           Optional[TurnoEnum] = None


# ─── Actualización (body del PATCH) ──────────────────────────────────────────
class UsuarioUpdate(BaseModel):
    nombre:          Optional[str] = None
    email:           Optional[EmailStr] = None
    codigo_empleado: Optional[str] = None
    rol:             Optional[RolEnum] = None
    id_sede:         Optional[str] = None
    turno:           Optional[TurnoEnum] = None
    activo:          Optional[bool] = None
