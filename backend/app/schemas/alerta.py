from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime


class AlertaRead(BaseModel):
    """Response schema para alertas — NUNCA incluir RUT (Ley 19.628)."""
    id: str
    id_container: str
    id_usuario_revision: Optional[str] = None
    tipo: str
    severidad: str
    descripcion: str
    estado: str
    fecha_generacion: Optional[datetime] = None
    fecha_revision: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AlertaRevisar(BaseModel):
    """PATCH /alertas/{id}/revisar — sin campos extra, el token firma."""
    pass


class AlertaResolver(BaseModel):
    """PATCH /alertas/{id}/resolver — observación opcional."""
    observacion: Optional[str] = None
