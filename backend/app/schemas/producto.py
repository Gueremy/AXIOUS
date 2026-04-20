from pydantic import BaseModel, ConfigDict
from typing import Optional

class ProductoBase(BaseModel):
    nombre: str
    codigo_barras: str
    categoria: str  # alimento, quimico, veterinario, equipo, repuesto, general
    descripcion: Optional[str] = None
    unidad_medida: str
    stock_minimo: float = 0.0

class ProductoCreate(ProductoBase):
    pass

class ProductoUpdate(BaseModel):
    nombre: Optional[str] = None
    codigo_barras: Optional[str] = None
    categoria: Optional[str] = None
    descripcion: Optional[str] = None
    unidad_medida: Optional[str] = None
    stock_minimo: Optional[float] = None

class ProductoRead(ProductoBase):
    id: str
    model_config = ConfigDict(from_attributes=True)
