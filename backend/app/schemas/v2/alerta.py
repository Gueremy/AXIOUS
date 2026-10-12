from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ReglaAlertaCreate(BaseModel):
    codigo: str = Field(..., max_length=50, description="Código único de la regla dentro de la organización")
    nombre: str = Field(..., max_length=100)
    tipo: str = Field(..., max_length=50, description="Categoría: capacidad, vencimiento, stock, inactividad, etc.")
    configuracion: Dict[str, Any] = Field(default_factory=dict, description="Parámetros dinámicos (umbrales, días, etc.)")
    severidad: str = Field(default="aviso", description="critica, aviso, o informativa")
    habilitada: bool = True


class ReglaAlertaUpdate(BaseModel):
    nombre: Optional[str] = Field(None, max_length=100)
    configuracion: Optional[Dict[str, Any]] = None
    severidad: Optional[str] = None
    habilitada: Optional[bool] = None


class ReglaAlertaRead(BaseModel):
    id: str
    id_organizacion: str
    codigo: str
    nombre: str
    tipo: str
    configuracion: Dict[str, Any]
    severidad: str
    habilitada: bool
    fecha_creacion: datetime
    fecha_actualizacion: datetime

    model_config = ConfigDict(from_attributes=True)


class AlertaRead(BaseModel):
    id: str
    id_organizacion: str
    id_regla: Optional[str] = None
    id_sitio: Optional[str] = None
    id_ubicacion: Optional[str] = None
    id_item: Optional[str] = None
    id_lote: Optional[str] = None
    tipo: str
    severidad: str
    titulo: str
    descripcion: str
    estado: str
    id_usuario_revision: Optional[str] = None
    fecha_generacion: datetime
    fecha_revision: Optional[datetime] = None
    fecha_resolucion: Optional[datetime] = None
    metadatos: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


class AlertaRevisar(BaseModel):
    observaciones: Optional[str] = Field(None, max_length=300)


class AlertaResolver(BaseModel):
    observaciones: Optional[str] = Field(None, max_length=300)


class EvaluarAlertasResultado(BaseModel):
    reglas_evaluadas: int
    nuevas_alertas: int
    alertas_creadas: List[AlertaRead]
