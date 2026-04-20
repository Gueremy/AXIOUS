from pydantic import BaseModel, ConfigDict
from typing import Optional

class SedeBase(BaseModel):
    nombre: str
    tipo: str  # "ponton", "planta", "bodega"
    ubicacion: Optional[str] = None
    latitud: Optional[float] = None
    longitud: Optional[float] = None
    capacidad_total: Optional[int] = None

class SedeCreate(SedeBase):
    pass

class SedeUpdate(BaseModel):
    nombre: Optional[str] = None
    tipo: Optional[str] = None
    ubicacion: Optional[str] = None
    latitud: Optional[float] = None
    longitud: Optional[float] = None
    capacidad_total: Optional[int] = None
    estado: Optional[str] = None

class SedeRead(SedeBase):
    id: str
    estado: str
    model_config = ConfigDict(from_attributes=True)
