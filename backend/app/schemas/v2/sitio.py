from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class SitioCreate(BaseModel):
    codigo: str = Field(..., max_length=50)
    nombre: str = Field(..., max_length=150)
    tipo: str = Field(..., max_length=50)
    descripcion: Optional[str] = Field(None, max_length=300)
    ubicacion_geografica: Optional[str] = Field(None, max_length=200)
    atributos: Dict[str, Any] = Field(default_factory=dict)


class SitioUpdate(BaseModel):
    nombre: Optional[str] = Field(None, max_length=150)
    tipo: Optional[str] = Field(None, max_length=50)
    descripcion: Optional[str] = Field(None, max_length=300)
    ubicacion_geografica: Optional[str] = Field(None, max_length=200)
    atributos: Optional[Dict[str, Any]] = None
    activo: Optional[bool] = None


class SitioRead(BaseModel):
    id: str
    id_organizacion: str
    codigo: str
    nombre: str
    tipo: str
    descripcion: Optional[str] = None
    ubicacion_geografica: Optional[str] = None
    atributos: Dict[str, Any] = Field(default_factory=dict)
    activo: bool
    fecha_creacion: datetime

    model_config = {"from_attributes": True}
