from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ItemCreate(BaseModel):
    codigo: str = Field(..., max_length=50)
    nombre: str = Field(..., max_length=150)
    categoria: str = Field(..., max_length=50)
    unidad_medida: str = Field(..., max_length=20)
    atributos: Dict[str, Any] = Field(default_factory=dict)


class ItemUpdate(BaseModel):
    nombre: Optional[str] = Field(None, max_length=150)
    categoria: Optional[str] = Field(None, max_length=50)
    unidad_medida: Optional[str] = Field(None, max_length=20)
    atributos: Optional[Dict[str, Any]] = None
    activo: Optional[bool] = None


class ItemRead(BaseModel):
    id: str
    id_organizacion: str
    codigo: str
    nombre: str
    categoria: str
    unidad_medida: str
    atributos: Dict[str, Any] = Field(default_factory=dict)
    activo: bool
    fecha_creacion: datetime

    model_config = {"from_attributes": True}
