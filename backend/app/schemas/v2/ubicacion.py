from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class UbicacionCreate(BaseModel):
    id_zona: str
    codigo: str = Field(..., max_length=50)
    capacidad_maxima: Decimal = Field(..., ge=0)
    unidad_capacidad: str = Field(..., max_length=20)
    permite_mezcla_lotes: bool = True
    estado: str = Field("disponible", max_length=30)
    layout: Dict[str, Any] = Field(default_factory=dict)
    atributos: Dict[str, Any] = Field(default_factory=dict)


class UbicacionUpdate(BaseModel):
    capacidad_maxima: Optional[Decimal] = Field(None, ge=0)
    unidad_capacidad: Optional[str] = Field(None, max_length=20)
    permite_mezcla_lotes: Optional[bool] = None
    estado: Optional[str] = Field(None, max_length=30)
    layout: Optional[Dict[str, Any]] = None
    atributos: Optional[Dict[str, Any]] = None
    activo: Optional[bool] = None


class UbicacionRead(BaseModel):
    id: str
    id_organizacion: str
    id_zona: str
    codigo: str
    capacidad_maxima: Decimal
    unidad_capacidad: str
    ocupacion_actual: Decimal
    permite_mezcla_lotes: bool
    estado: str
    layout: Dict[str, Any] = Field(default_factory=dict)
    atributos: Dict[str, Any] = Field(default_factory=dict)
    activo: bool
    fecha_creacion: datetime

    model_config = {"from_attributes": True}
