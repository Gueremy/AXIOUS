from datetime import datetime
from typing import Any, Dict
from pydantic import BaseModel, Field


class EsquemaAtributosCreate(BaseModel):
    entidad: str = Field(..., max_length=50)
    nombre: str = Field(..., max_length=100)
    version: int = Field(1, ge=1)
    definicion_schema: Dict[str, Any] = Field(..., alias="schema_json")

    model_config = {"populate_by_name": True}


class EsquemaAtributosRead(BaseModel):
    id: str
    id_organizacion: str
    entidad: str
    nombre: str
    version: int
    definicion_schema: Dict[str, Any] = Field(..., alias="schema_json")
    activo: bool
    fecha_creacion: datetime

    model_config = {
        "populate_by_name": True,
        "from_attributes": True,
    }
