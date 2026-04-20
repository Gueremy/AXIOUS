from pydantic import BaseModel, ConfigDict, Field
from typing import Optional

class ContainerBase(BaseModel):
    codigo: str
    id_galpon: str
    posicion_fila: int
    posicion_col: int
    estado: str = "disponible" # disponible, medio, critico, mantenimiento, cuarentena
    tipo_producto_permitido: str
    capacidad_max: float
    ocupacion_actual: float = 0.0
    unidad_medida: str

class ContainerCreate(ContainerBase):
    pass

class ContainerUpdate(BaseModel):
    codigo: Optional[str] = None
    id_galpon: Optional[str] = None
    posicion_fila: Optional[int] = None
    posicion_col: Optional[int] = None
    estado: Optional[str] = None
    tipo_producto_permitido: Optional[str] = None
    capacidad_max: Optional[float] = None
    ocupacion_actual: Optional[float] = None
    unidad_medida: Optional[str] = None

class ContainerRead(ContainerBase):
    id: str
    model_config = ConfigDict(from_attributes=True)
