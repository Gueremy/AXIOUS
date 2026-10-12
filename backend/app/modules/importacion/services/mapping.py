from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple


class MappingService:
    """
    Servicio de normalización de registros externos utilizando perfiles de mapeo configurables.
    """

    @staticmethod
    def normalizar_filas(
        filas_crudas: List[Dict[str, Any]],
        mapeo: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        """
        Transforma una lista de diccionarios crudos a la estructura canónica requerida por el conciliador.
        Mapeo esperado:
            'codigo_ubicacion': 'POS'
            'codigo_item': 'SKU'
            'cantidad': 'QTY'
            'numero_lote': 'LOTE' (opcional)
        """
        col_ubicacion = mapeo.get("codigo_ubicacion")
        col_item = mapeo.get("codigo_item")
        col_cantidad = mapeo.get("cantidad")
        col_lote = mapeo.get("numero_lote")

        filas_normalizadas = []
        for idx, fila in enumerate(filas_crudas, start=2):  # start=2 para reflejar número de fila con cabecera en fila 1
            codigo_ubi = str(fila.get(col_ubicacion)).strip() if col_ubicacion and fila.get(col_ubicacion) is not None else None
            codigo_item = str(fila.get(col_item)).strip() if col_item and fila.get(col_item) is not None else None
            num_lote = str(fila.get(col_lote)).strip() if col_lote and fila.get(col_lote) is not None else None

            # Parsear cantidad numérica
            val_cant = fila.get(col_cantidad)
            cantidad = None
            if val_cant is not None:
                try:
                    if isinstance(val_cant, (int, float)):
                        cantidad = Decimal(str(val_cant))
                    else:
                        cant_str = str(val_cant).replace(",", ".").strip()
                        cantidad = Decimal(cant_str)
                except Exception:
                    cantidad = None

            filas_normalizadas.append({
                "fila": idx,
                "codigo_ubicacion": codigo_ubi,
                "codigo_item": codigo_item,
                "numero_lote": num_lote,
                "cantidad": cantidad,
                "datos_crudos": fila,
            })

        return filas_normalizadas
