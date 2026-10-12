from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class ModuloItemRead(BaseModel):
    id: str
    nombre: str
    version: str
    descripcion: str
    habilitado: bool
    rutas_api: str
    configuracion: Dict[str, Any]


class ModuloEstadoUpdate(BaseModel):
    habilitado: bool
    configuracion: Optional[Dict[str, Any]] = None
