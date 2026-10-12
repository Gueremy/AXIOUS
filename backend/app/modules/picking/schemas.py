from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, Field


class PickingSugerenciaItem(BaseModel):
    id_ubicacion: str
    codigo_ubicacion: str
    id_lote: Optional[str] = None
    numero_lote: Optional[str] = None
    cantidad_disponible: Decimal
    cantidad_sugerida: Decimal
    fecha_vencimiento: Optional[datetime] = None


class PickingPlanResponse(BaseModel):
    estrategia: str
    id_item: str
    cantidad_solicitada: Decimal
    cantidad_asignada: Decimal
    completado: bool
    sugerencias: List[PickingSugerenciaItem]
