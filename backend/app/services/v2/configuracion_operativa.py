"""Configuración operativa por organización sin alterar los datos del núcleo."""
from decimal import Decimal

from fastapi import HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.v2.organizacion import Organizacion


class UnidadConfig(BaseModel):
    dimension: str = Field(..., min_length=1, max_length=30)
    factor: Decimal = Field(..., gt=0)


class UmbralesColor(BaseModel):
    alerta: float = Field(40, ge=0, le=100)
    critica: float = Field(80, ge=0, le=100)

    @model_validator(mode="after")
    def ordenados(self):
        if self.alerta >= self.critica:
            raise ValueError("El umbral de alerta debe ser menor al crítico")
        return self


class ConfiguracionOperativa(BaseModel):
    umbrales_color: UmbralesColor = Field(default_factory=UmbralesColor)
    paleta_colores: dict[str, str] = Field(default_factory=lambda: {
        "libre": "#94A3B8", "optima": "#22C55E", "alerta": "#F59E0B",
        "critica": "#EF4444", "retenido": "#7C3AED",
    })
    unidades: dict[str, UnidadConfig] = Field(default_factory=dict)


UNIDADES_BASE = {
    "kg": UnidadConfig(dimension="masa", factor=Decimal("1")),
    "tonelada": UnidadConfig(dimension="masa", factor=Decimal("1000")),
    "t": UnidadConfig(dimension="masa", factor=Decimal("1000")),
    "litro": UnidadConfig(dimension="volumen", factor=Decimal("1")),
    "l": UnidadConfig(dimension="volumen", factor=Decimal("1")),
    "m3": UnidadConfig(dimension="volumen", factor=Decimal("1000")),
    "unidad": UnidadConfig(dimension="unidades", factor=Decimal("1")),
    "unidades": UnidadConfig(dimension="unidades", factor=Decimal("1")),
    "pallet": UnidadConfig(dimension="pallets", factor=Decimal("1")),
    "pallets": UnidadConfig(dimension="pallets", factor=Decimal("1")),
    "slot": UnidadConfig(dimension="slots", factor=Decimal("1")),
    "slots": UnidadConfig(dimension="slots", factor=Decimal("1")),
}


def leer_configuracion(org: Organizacion) -> ConfiguracionOperativa:
    raw = (org.configuracion or {}).get("operativa", {})
    unidades = dict(UNIDADES_BASE)
    unidades.update({k: UnidadConfig.model_validate(v) for k, v in raw.get("unidades", {}).items()})
    return ConfiguracionOperativa(
        umbrales_color=UmbralesColor.model_validate(raw.get("umbrales_color", {})),
        paleta_colores={**ConfiguracionOperativa().paleta_colores,
                        **raw.get("paleta_colores", {})},
        unidades=unidades,
    )


async def obtener_configuracion(db: AsyncSession, id_organizacion: str) -> ConfiguracionOperativa:
    org = (await db.execute(select(Organizacion).where(
        Organizacion.id == id_organizacion,
    ))).scalar_one()
    return leer_configuracion(org)


def convertir_cantidad(cantidad: Decimal, origen: str, destino: str,
                      config: ConfiguracionOperativa) -> Decimal:
    if origen == destino:
        return cantidad
    origen_cfg = config.unidades.get(origen)
    destino_cfg = config.unidades.get(destino)
    if not origen_cfg or not destino_cfg or origen_cfg.dimension != destino_cfg.dimension:
        raise HTTPException(status_code=400, detail=f"Unidades incompatibles: '{origen}' y '{destino}'")
    resultado = cantidad * origen_cfg.factor / destino_cfg.factor
    if resultado != resultado.quantize(Decimal("0.0001")):
        raise HTTPException(status_code=400, detail="La conversión excede la precisión de 4 decimales de la capacidad")
    return resultado
