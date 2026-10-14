from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class MappingProfileCreate(BaseModel):
    nombre: str = Field(..., max_length=100)
    descripcion: Optional[str] = Field(None, max_length=255)
    mapeo: Dict[str, str] = Field(
        ...,
        description="Diccionario de mapeo de nombres de columna externa a campos canónicos: "
                    "{'codigo_ubicacion': 'POS', 'codigo_item': 'SKU', 'cantidad': 'QTY', 'numero_lote': 'LOTE'}"
    )


class MappingProfileUpdate(BaseModel):
    nombre: Optional[str] = Field(None, max_length=100)
    descripcion: Optional[str] = Field(None, max_length=255)
    mapeo: Optional[Dict[str, str]] = None
    activo: Optional[bool] = None


class MappingProfileRead(BaseModel):
    id: str
    id_organizacion: str
    nombre: str
    descripcion: Optional[str] = None
    mapeo: Dict[str, str]
    activo: bool
    fecha_creacion: datetime

    model_config = ConfigDict(from_attributes=True)


class InconsistenciaRead(BaseModel):
    id: str
    id_ubicacion: Optional[str] = None
    id_importacion_job: str
    fila_origen: int
    tipo_inconsistencia: str
    motivo: str
    codigo_ubicacion: Optional[str] = None
    codigo_item: Optional[str] = None
    numero_lote: Optional[str] = None
    cantidad_externa: Optional[Decimal] = None
    datos_crudos: Dict[str, Any] = Field(default_factory=dict)
    resuelto: bool
    fecha_deteccion: datetime

    model_config = ConfigDict(from_attributes=True)


class ImportacionJobRead(BaseModel):
    id: str
    id_organizacion: str
    id_mapping_profile: Optional[str] = None
    nombre_archivo: str
    tipo_fuente: str
    estado: str
    total_registros: int
    registros_validos: int
    registros_inconsistentes: int
    fecha_inicio: datetime
    fecha_fin: Optional[datetime] = None
    resumen: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class ConciliacionResultado(BaseModel):
    job: ImportacionJobRead
    inconsistencias: List[InconsistenciaRead]


class ImportacionAPIRequest(BaseModel):
    fuente: str = Field(..., min_length=1, max_length=100)
    filas: List[Dict[str, Any]] = Field(..., min_length=1, max_length=10000)
    id_mapping_profile: Optional[str] = None
    mapeo: Optional[Dict[str, str]] = None
