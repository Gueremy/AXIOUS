from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class LayoutCoordinates(BaseModel):
    x: float = Field(0.0, description="Posición X en plano 2D/3D")
    y: float = Field(0.0, description="Posición Y en plano 2D/3D")
    z: float = Field(0.0, description="Nivel/Altura Z")
    width: Optional[float] = Field(None, description="Ancho")
    height: Optional[float] = Field(None, description="Alto")
    depth: Optional[float] = Field(None, description="Profundidad")
    color: Optional[str] = Field(None, description="Color hexadecimal de renderizado")
    rotation: Optional[float] = Field(0.0, description="Ángulo de rotación en grados")


class LayoutUpdate(BaseModel):
    layout: Dict[str, Any] = Field(..., description="Estructura de posicionamiento y dimensiones espaciales")


class UbicacionBatchItem(BaseModel):
    codigo: str
    capacidad_maxima: Decimal = Field(..., gt=0)
    unidad_capacidad: str
    layout: Dict[str, Any] = Field(default_factory=dict)
    permite_mezcla_lotes: bool = True


class UbicacionBatchCreate(BaseModel):
    id_zona: str
    ubicaciones: List[UbicacionBatchItem]


class LayoutUbicacionNode(BaseModel):
    id: str
    codigo: str
    capacidad_maxima: Decimal
    ocupacion_actual: Decimal
    porcentaje_ocupacion: float
    unidad_capacidad: str
    estado: str
    permite_mezcla_lotes: bool
    layout: Dict[str, Any]


class LayoutZonaNode(BaseModel):
    id: str
    codigo: str
    nombre: str
    tipo: str
    layout: Dict[str, Any]
    subzonas: List["LayoutZonaNode"] = []
    ubicaciones: List[LayoutUbicacionNode] = []


class LayoutSitioTree(BaseModel):
    id_sitio: str
    codigo: str
    nombre: str
    tipo: str
    zonas: List[LayoutZonaNode]
