from pydantic import BaseModel, ConfigDict
from typing import Optional

class GalponBase(BaseModel):
    nombre: str
    codigo: str
    id_sede: str
    filas: int
    columnas: int

class GalponCreate(GalponBase):
    pass

class GalponUpdate(BaseModel):
    nombre: Optional[str] = None
    codigo: Optional[str] = None
    id_sede: Optional[str] = None
    filas: Optional[int] = None
    columnas: Optional[int] = None
    estado: Optional[str] = None

class GalponRead(GalponBase):
    id: str
    model_config = ConfigDict(from_attributes=True)
