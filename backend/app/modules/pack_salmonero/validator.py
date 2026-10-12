"""
app/modules/pack_salmonero/validator.py
Validaciones normativas y regulatorias de acuicultura (SERNAPESCA / SAG) — Fase 2D.
Sólo se ejecutan cuando el módulo 'pack_salmonero' está activo para la organización.
"""
from typing import Dict, Any
from fastapi import HTTPException, status


def validar_atributos_salmoneros(atributos: Dict[str, Any]) -> None:
    """
    Exige la presencia de identificadores normativos de acuicultura chilena:
    - codigo_concesion_sernapesca (ej: 'RES-SERNA-10293')
    - autorizacion_sag (ej: 'SAG-CERT-4491')
    """
    if not atributos.get("codigo_concesion_sernapesca"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pack Salmonero activo: El movimiento exige el atributo 'codigo_concesion_sernapesca' (Ley General de Pesca y Acuicultura).",
        )
    if not atributos.get("autorizacion_sag"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pack Salmonero activo: El movimiento exige el atributo 'autorizacion_sag' (control fitosanitario SAG).",
        )
