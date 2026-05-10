from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import Optional
from datetime import datetime

class MovimientoBase(BaseModel):
    id_container: str
    id_producto: str
    tipo: str  # entrada_proveedor, salida_produccion, traslado_interno, correccion
    cantidad: Decimal
    numero_lote: str

    # Campos SERNAPESCA
    fecha_fabricacion: Optional[datetime] = None
    fecha_vencimiento: Optional[datetime] = None
    nombre_proveedor: Optional[str] = None
    rut_proveedor: Optional[str] = None
    num_guia_despacho: Optional[str] = None
    registro_sanitario: Optional[str] = None
    temperatura_almacen: Optional[float] = None

    # Campos SAG
    num_receta_retenida: Optional[str] = None
    num_autorizacion_sag: Optional[str] = None

    # Opcionales
    id_container_destino: Optional[str] = None
    observaciones: Optional[str] = None
    id_movimiento_original: Optional[str] = None

class MovimientoCreate(MovimientoBase):
    @field_validator("cantidad")
    @classmethod
    def validar_cantidad(cls, v):
        if v <= 0 or v >= 999999:
            raise ValueError("La cantidad debe ser mayor a 0 y menor a 999,999")
        return v

    @model_validator(mode="after")
    def validar_sernapesca(self):
        if self.tipo == "entrada_proveedor":
            if not self.fecha_fabricacion:
                raise ValueError("fecha_fabricacion requerida por SERNAPESCA para entradas")
            if not self.fecha_vencimiento:
                raise ValueError("fecha_vencimiento requerida por SERNAPESCA para entradas")
            if not self.nombre_proveedor:
                raise ValueError("nombre_proveedor requerido por SERNAPESCA para entradas")
            if not self.num_guia_despacho:
                raise ValueError("num_guia_despacho requerida por SERNAPESCA para entradas")
            if self.temperatura_almacen is None:
                raise ValueError("temperatura_almacen requerida por SERNAPESCA para entradas")
            if not self.registro_sanitario:
                raise ValueError("registro_sanitario requerido por SERNAPESCA para entradas")
        
        if self.tipo == "traslado_interno" and not self.id_container_destino:
            raise ValueError("id_container_destino es obligatorio para traslados")

        return self

class MovimientoOfflineCreate(BaseModel):
    """Schema para movimientos creados offline en Dexie.js."""
    uuid_local:          str = ""
    id_container:        str
    id_producto:         str
    tipo:                str
    cantidad:            Decimal = Field(gt=0, lt=999999)
    numero_lote:         str = "OFFLINE"
    fecha_vencimiento:   Optional[datetime] = None
    nombre_proveedor:    Optional[str] = None
    num_guia_despacho:   Optional[str] = None
    registro_sanitario:  Optional[str] = None
    temperatura_almacen: Optional[float] = None
    observaciones:       Optional[str] = None

    @field_validator("tipo")
    @classmethod
    def validar_tipo(cls, v: str) -> str:
        allowed = {"entrada_proveedor", "salida_produccion", "traslado_interno"}
        if v not in allowed:
            raise ValueError(f"tipo debe ser uno de: {', '.join(sorted(allowed))}")
        return v


class MovimientoAprobar(BaseModel):
    pass

class MovimientoRechazar(BaseModel):
    motivo_rechazo: str

class MovimientoRead(BaseModel):
    id: str
    id_container: str
    id_producto: str
    id_usuario: str
    id_usuario_aprobador: Optional[str] = None
    tipo: str
    estado: str
    cantidad: Decimal
    numero_lote: str

    fecha_fabricacion: Optional[datetime] = None
    fecha_vencimiento: Optional[datetime] = None
    nombre_proveedor: Optional[str] = None
    # rut_proveedor NO se expone aquí (Cumplimiento Ley 19.628)
    num_guia_despacho: Optional[str] = None
    registro_sanitario: Optional[str] = None
    temperatura_almacen: Optional[float] = None
    
    num_receta_retenida: Optional[str] = None
    num_autorizacion_sag: Optional[str] = None
    
    fecha_hora: datetime
    fecha_aprobacion: Optional[datetime] = None
    motivo_rechazo: Optional[str] = None
    observaciones: Optional[str] = None
    origen: str

    model_config = ConfigDict(from_attributes=True)
