from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, ConfigDict


class DashboardKPIs(BaseModel):
    """Cinco indicadores mínimos requeridos para supervisor (Fase 1F)."""
    capacidad_instalada: Decimal
    stock_total: Decimal
    ubicaciones_libres: int
    porcentaje_uso: float
    cantidad_inconsistencias: int
    total_ubicaciones: int
    total_items: int
    alertas_activas: int

    model_config = ConfigDict(from_attributes=True)


class UbicacionOcupacionItem(BaseModel):
    id_ubicacion: str
    codigo: str
    capacidad_maxima: Decimal
    ocupacion_actual: Decimal
    porcentaje_ocupacion: float
    unidad_capacidad: str
    estado: str


class InconsistenciaDashboardItem(BaseModel):
    id: str
    id_ubicacion: Optional[str] = None
    id_job: str
    fila_origen: int
    tipo_inconsistencia: str
    motivo: str
    codigo_ubicacion: Optional[str] = None
    codigo_item: Optional[str] = None
    numero_lote: Optional[str] = None
    cantidad_externa: Optional[Decimal] = None
    fecha_deteccion: str


class EvolucionMovimientoItem(BaseModel):
    fecha: str
    entradas: int
    salidas: int
    traslados: int
    total: int
