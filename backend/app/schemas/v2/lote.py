from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class LoteCreate(BaseModel):
    id_item: str
    numero_lote: str = Field(..., max_length=100)
    fecha_fabricacion: Optional[datetime] = None
    fecha_vencimiento: Optional[datetime] = None
    atributos: Dict[str, Any] = Field(default_factory=dict)
    estado: str = Field("activo", max_length=30)


class LoteUpdate(BaseModel):
    fecha_fabricacion: Optional[datetime] = None
    fecha_vencimiento: Optional[datetime] = None
    atributos: Optional[Dict[str, Any]] = None
    estado: Optional[str] = Field(None, max_length=30)


class LoteRead(BaseModel):
    id: str
    id_organizacion: str
    id_item: str
    numero_lote: str
    fecha_fabricacion: Optional[datetime] = None
    fecha_vencimiento: Optional[datetime] = None
    atributos: Dict[str, Any] = Field(default_factory=dict)
    estado: str
    fecha_creacion: datetime

    model_config = {"from_attributes": True}
