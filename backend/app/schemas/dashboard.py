from pydantic import BaseModel, ConfigDict, computed_field
from typing import Optional


class KPIResponse(BaseModel):
    """KPIs globales de la sede."""
    model_config = ConfigDict(populate_by_name=True)

    ocupacion_global: float
    ocupacion_global_pct: float = 0.0   # alias descriptivo — mismo valor que ocupacion_global
    alertas_activas: int
    movimientos_hoy: int
    proximo_vencimiento: Optional[int] = None      # None si no hay lotes con vencimiento
    proximo_vencimiento_dias: Optional[int] = None  # alias descriptivo — mismo valor


class OcupacionGalponItem(BaseModel):
    """Ocupación por galpón — formato Recharts BarChart."""
    name: str              # nombre del galpón
    ocupacion_pct: float   # porcentaje 0-100
    ocup: float            # BUG-3 FIX: alias que espera el frontend (mismo valor que ocupacion_pct)
    estado: str            # "disponible" | "medio" | "critico"


class EvolucionItem(BaseModel):
    """Evolución de movimientos por día — formato Recharts LineChart."""
    fecha: str             # "YYYY-MM-DD"
    movimientos: int       # total movimientos aprobados ese día
    entradas: int
    salidas: int
