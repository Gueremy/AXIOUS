from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel, Field


class TipoMovimientoCreate(BaseModel):
    codigo: str = Field(..., max_length=50)
    nombre: str = Field(..., max_length=100)
    efecto_stock: Literal["entrada", "salida", "traslado", "sin_efecto"]
    requiere_origen: bool = False
    requiere_destino: bool = False
    requiere_aprobacion: bool = False


class TipoMovimientoRead(BaseModel):
    id: str
    id_organizacion: str
    codigo: str
    nombre: str
    efecto_stock: str
    requiere_origen: bool
    requiere_destino: bool
    requiere_aprobacion: bool
    activo: bool

    model_config = {"from_attributes": True}


class SolicitudMovimientoCreate(BaseModel):
    id_tipo_movimiento: str
    id_item: str
    id_lote: Optional[str] = None
    id_ubicacion_origen: Optional[str] = None
    id_ubicacion_destino: Optional[str] = None
    cantidad: Decimal = Field(..., gt=0)
    unidad_medida: str = Field(..., max_length=20)
    observaciones: Optional[str] = Field(None, max_length=300)
    uuid_local: Optional[str] = None
    atributos: Dict[str, Any] = Field(default_factory=dict)


class SolicitudRechazar(BaseModel):
    motivo: str = Field(..., min_length=3, max_length=300)


class SolicitudMovimientoRead(BaseModel):
    id: str
    id_organizacion: str
    id_tipo_movimiento: str
    id_item: str
    id_lote: Optional[str] = None
    id_ubicacion_origen: Optional[str] = None
    id_ubicacion_destino: Optional[str] = None
    id_usuario_solicitante: str
    id_usuario_aprobador: Optional[str] = None
    cantidad: Decimal
    unidad_medida: str
    estado: str
    motivo_rechazo: Optional[str] = None
    observaciones: Optional[str] = None
    uuid_local: Optional[str] = None
    atributos: Dict[str, Any] = Field(default_factory=dict)
    fecha_creacion: datetime
    fecha_resolucion: Optional[datetime] = None

    model_config = {"from_attributes": True}


class MovimientoV2Read(BaseModel):
    id: str
    id_organizacion: str
    id_solicitud: Optional[str] = None
    id_tipo_movimiento: str
    id_movimiento_original: Optional[str] = None
    id_item: str
    id_lote: Optional[str] = None
    id_ubicacion_origen: Optional[str] = None
    id_ubicacion_destino: Optional[str] = None
    id_usuario: str
    id_usuario_aprobador: Optional[str] = None
    cantidad: Decimal
    unidad_medida: str
    efecto_stock: str
    uuid_local: Optional[str] = None
    atributos: Dict[str, Any] = Field(default_factory=dict)
    fecha_hora: datetime
    observaciones: Optional[str] = None

    model_config = {"from_attributes": True}


class SaldoStockRead(BaseModel):
    id: str
    id_organizacion: str
    id_ubicacion: str
    id_item: str
    id_lote: Optional[str] = None
    cantidad: Decimal
    unidad_medida: str
    fecha_actualizacion: datetime

    model_config = {"from_attributes": True}
