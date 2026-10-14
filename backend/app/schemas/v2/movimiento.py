from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel, Field, model_validator


class EtapaAprobacion(BaseModel):
    codigo: str = Field(..., min_length=1, max_length=20, pattern=r"^[a-zA-Z0-9_]+$")
    roles: list[str] = Field(default_factory=list)


class FlujoAprobacion(BaseModel):
    etapas: list[EtapaAprobacion] = Field(default_factory=list, max_length=5)
    estado_aprobado: str = Field("aprobada", min_length=1, max_length=20)
    estado_rechazado: str = Field("rechazada", min_length=1, max_length=20)

    @model_validator(mode="after")
    def validar_estados(self):
        codigos = [etapa.codigo for etapa in self.etapas]
        if len(set(codigos + [self.estado_aprobado, self.estado_rechazado])) != len(codigos) + 2:
            raise ValueError("Los estados del flujo deben ser distintos")
        return self


class TipoMovimientoCreate(BaseModel):
    codigo: str = Field(..., max_length=50)
    nombre: str = Field(..., max_length=100)
    efecto_stock: Literal["entrada", "salida", "traslado", "sin_efecto"]
    requiere_origen: bool = False
    requiere_destino: bool = False
    requiere_aprobacion: bool = False
    flujo_aprobacion: Optional[FlujoAprobacion] = None

    @model_validator(mode="after")
    def validar_flujo(self):
        if self.flujo_aprobacion and self.flujo_aprobacion.etapas and not self.requiere_aprobacion:
            raise ValueError("Las etapas requieren aprobación activada")
        return self


class TipoMovimientoUpdate(BaseModel):
    nombre: Optional[str] = Field(None, max_length=100)
    requiere_aprobacion: Optional[bool] = None
    flujo_aprobacion: Optional[FlujoAprobacion] = None
    activo: Optional[bool] = None


class TipoMovimientoRead(BaseModel):
    id: str
    id_organizacion: str
    codigo: str
    nombre: str
    efecto_stock: str
    requiere_origen: bool
    requiere_destino: bool
    requiere_aprobacion: bool
    flujo_aprobacion: Dict[str, Any] = Field(default_factory=dict)
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
