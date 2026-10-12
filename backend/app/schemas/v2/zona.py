from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ZonaCreate(BaseModel):
    id_sitio: str
    id_zona_padre: Optional[str] = None
    codigo: str = Field(..., max_length=50)
    nombre: str = Field(..., max_length=150)
    tipo: str = Field(..., max_length=50)
    layout: Dict[str, Any] = Field(default_factory=dict)
    atributos: Dict[str, Any] = Field(default_factory=dict)


class ZonaUpdate(BaseModel):
    nombre: Optional[str] = Field(None, max_length=150)
    tipo: Optional[str] = Field(None, max_length=50)
    layout: Optional[Dict[str, Any]] = None
    atributos: Optional[Dict[str, Any]] = None
    activo: Optional[bool] = None


class ZonaRead(BaseModel):
    id: str
    id_organizacion: str
    id_sitio: str
    id_zona_padre: Optional[str] = None
    codigo: str
    nombre: str
    tipo: str
    layout: Dict[str, Any] = Field(default_factory=dict)
    atributos: Dict[str, Any] = Field(default_factory=dict)
    activo: bool
    fecha_creacion: datetime

    model_config = {"from_attributes": True}


class ZonaTreeRead(ZonaRead):
    hijos: List["ZonaTreeRead"] = Field(default_factory=list)

    model_config = {"from_attributes": True}
