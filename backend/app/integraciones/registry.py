"""
app/integraciones/registry.py
Registro central de conectores externos (Fase 4).
"""
from typing import Dict, List, Optional
from app.integraciones.base import Conector, ConectorMockERP


class ConectorRegistry:
    _conectores: Dict[str, Conector] = {
        "mock_erp": ConectorMockERP(),
    }

    @classmethod
    def registrar(cls, conector: Conector) -> None:
        cls._conectores[conector.id] = conector

    @classmethod
    def obtener(cls, id_conector: str) -> Optional[Conector]:
        return cls._conectores.get(id_conector)

    @classmethod
    def listar(cls) -> List[Dict[str, str]]:
        return [{"id": c.id, "nombre": c.nombre} for c in cls._conectores.values()]
