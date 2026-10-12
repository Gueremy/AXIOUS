from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ReglaUbicacionCreate(BaseModel):
    codigo: str = Field(..., max_length=50)
    nombre: str = Field(..., max_length=100)
    tipo_regla: str = Field(..., max_length=50)  # 'mezcla_lotes', 'categorias_permitidas', 'items_permitidos', 'capacidad'
    id_sitio: Optional[str] = None
    id_zona: Optional[str] = None
    id_ubicacion: Optional[str] = None
    configuracion: Dict[str, Any] = Field(default_factory=dict)


class ReglaUbicacionUpdate(BaseModel):
    nombre: Optional[str] = Field(None, max_length=100)
    configuracion: Optional[Dict[str, Any]] = None
    activo: Optional[bool] = None


class ReglaUbicacionRead(BaseModel):
    id: str
    id_organizacion: str
    id_sitio: Optional[str] = None
    id_zona: Optional[str] = None
    id_ubicacion: Optional[str] = None
    codigo: str
    nombre: str
    tipo_regla: str
    configuracion: Dict[str, Any]
    activo: bool
    fecha_creacion: datetime

    model_config = {"from_attributes": True}
