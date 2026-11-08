from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class ProveedorData(BaseModel):
    rut: str
    razon_social: str = Field(..., min_length=2, max_length=150)

    @field_validator("rut")
    @classmethod
    def normalizar_rut(cls, value):
        compact = value.replace(".", "").replace("-", "").replace(" ", "").upper()
        if len(compact) not in (8, 9) or not compact[:-1].isdigit():
            raise ValueError("Ingresa un RUT de proveedor válido, con dígito verificador")
        body, digit = compact[:-1], compact[-1]
        total = sum(int(number) * (2 + index % 6) for index, number in enumerate(reversed(body)))
        result = 11 - total % 11
        expected = "0" if result == 11 else "K" if result == 10 else str(result)
        if digit != expected or int(body) == 0:
            raise ValueError("El dígito verificador del RUT de proveedor no coincide")
        return f"{body}-{digit}"

    @field_validator("razon_social")
    @classmethod
    def strip_name(cls, value):
        if len(value.strip()) < 2:
            raise ValueError("Ingresa la razón social del proveedor")
        return value.strip()


class LoteNuevo(BaseModel):
    numero_lote: str = Field(..., min_length=1, max_length=100)
    fecha_fabricacion: Optional[datetime] = None
    fecha_vencimiento: Optional[datetime] = None
    proveedor: ProveedorData

    @model_validator(mode="after")
    def validar_fechas(self):
        if self.fecha_fabricacion and self.fecha_vencimiento and self.fecha_fabricacion > self.fecha_vencimiento:
            raise ValueError("La fabricación debe ser anterior al vencimiento")
        self.numero_lote = self.numero_lote.strip()
        if not self.numero_lote:
            raise ValueError("Ingresa el número de lote")
        return self
