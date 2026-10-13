from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SyncMovimientoItem(BaseModel):
    uuid_local: str = Field(..., description="UUID generado en el cliente local (Dexie.js / PWA)")
    id_tipo_movimiento: str
    id_item: str
    id_lote: Optional[str] = None
    id_ubicacion_origen: Optional[str] = None
    id_ubicacion_destino: Optional[str] = None
    cantidad: Decimal = Field(..., gt=0)
    unidad_medida: str = Field(..., max_length=20)
    fecha_hora_local: Optional[datetime] = None
    observaciones: Optional[str] = Field(None, max_length=300)
    atributos: Dict[str, Any] = Field(default_factory=dict)


class SyncBatchRequest(BaseModel):
    movimientos: List[SyncMovimientoItem] = Field(..., min_length=1, max_length=100)


class SyncMovimientoResultado(BaseModel):
    uuid_local: str
    estado: str  # 'sincronizado', 'pendiente', 'duplicado', 'rechazado'
    id_movimiento: Optional[str] = None
    id_solicitud: Optional[str] = None
    motivo: Optional[str] = None


class SyncBatchResponse(BaseModel):
    total: int
    sincronizados: int
    pendientes: int = 0
    rechazados: int
    resultados: List[SyncMovimientoResultado]
