from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict


class BISitioDimension(BaseModel):
    id_sitio: str
    codigo_sitio: str
    nombre_sitio: str
    tipo_sitio: str
    total_zonas: int
    total_ubicaciones: int
    capacidad_total: Decimal

    model_config = ConfigDict(from_attributes=True)


class BIItemDimension(BaseModel):
    id_item: str
    codigo_item: str
    nombre_item: str
    categoria: str
    unidad_medida: str
    activo: bool

    model_config = ConfigDict(from_attributes=True)


class BIStockFact(BaseModel):
    id_ubicacion: str
    codigo_ubicacion: str
    id_sitio: str
    codigo_sitio: str
    id_item: str
    codigo_item: str
    id_lote: Optional[str] = None
    numero_lote: Optional[str] = None
    cantidad_saldo: Decimal
    unidad_medida: str
    capacidad_maxima: Decimal
    ocupacion_actual: Decimal
    porcentaje_ocupacion: float
    fecha_actualizacion: datetime

    model_config = ConfigDict(from_attributes=True)


class BIMovimientoFact(BaseModel):
    id_movimiento: str
    fecha_hora: datetime
    id_tipo_movimiento: str
    tipo_movimiento_codigo: str
    efecto_stock: str
    codigo_item: str
    numero_lote: Optional[str] = None
    codigo_ubicacion_origen: Optional[str] = None
    codigo_ubicacion_destino: Optional[str] = None
    cantidad: Decimal
    unidad_medida: str
    codigo_empleado_operario: str  # Código de empleado (NUNCA RUT, Ley 19.628)

    model_config = ConfigDict(from_attributes=True)


class BIInconsistenciaFact(BaseModel):
    id_inconsistencia: str
    id_ubicacion: Optional[str] = None
    fecha_deteccion: datetime
    tipo_inconsistencia: str
    codigo_ubicacion: Optional[str] = None
    codigo_item: Optional[str] = None
    numero_lote: Optional[str] = None
    cantidad_externa: Optional[Decimal] = None
    resuelto: bool

    model_config = ConfigDict(from_attributes=True)
