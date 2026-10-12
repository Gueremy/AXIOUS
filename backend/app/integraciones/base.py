"""
app/integraciones/base.py
Protocolo base para conectores de integración externa (Fase 4).
"""
from typing import Any, Dict, List, Protocol, runtime_checkable


@runtime_checkable
class Conector(Protocol):
    id: str
    nombre: str

    def probar_conexion(self, config: Dict[str, Any]) -> bool:
        """Prueba credenciales o conectividad hacia el sistema externo."""
        ...

    def leer(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extrae existencias o transacciones desde la fuente externa."""
        ...

    def escribir(self, config: Dict[str, Any], evento: Dict[str, Any]) -> bool:
        """Emite una actualización o movimiento hacia el sistema externo."""
        ...


class ConectorMockERP:
    id = "mock_erp"
    nombre = "Conector Simulado ERP / SAP RFC"

    def probar_conexion(self, config: Dict[str, Any]) -> bool:
        return bool(config.get("api_key") or config.get("host"))

    def leer(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [
            {"POS": "UBI-01", "SKU": "ITEM-100", "QTY": 50.0, "LOT": "LOTE-SAP-1"}
        ]

    def escribir(self, config: Dict[str, Any], evento: Dict[str, Any]) -> bool:
        return True
