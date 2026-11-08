from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from fastapi import HTTPException


def validar_mapeo(mapeo):
    if not isinstance(mapeo, dict):
        raise ValueError("El mapeo debe ser un diccionario")
    for key, value in mapeo.items():
        if key == "__equivalencias":
            if not isinstance(value, dict):
                raise ValueError("Las equivalencias deben asociar códigos externos con ubicaciones")
            for external, target in value.items():
                if not isinstance(external, str) or not external.strip() or not isinstance(target, dict):
                    raise ValueError("Revisa el código externo de cada equivalencia")
                if not all(isinstance(target.get(field), str) and target[field].strip()
                           for field in ("codigo_sitio", "codigo_zona", "codigo_ubicacion")):
                    raise ValueError("Cada equivalencia requiere sede, zona y ubicación de destino")
        elif not isinstance(value, str):
            raise ValueError("Los nombres de columna del mapeo deben ser texto")
    return mapeo


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
        try:
            validar_mapeo(mapeo)
        except ValueError as exc:
            raise HTTPException(422, detail=str(exc)) from exc
        col_ubicacion = mapeo.get("codigo_ubicacion")
        col_item = mapeo.get("codigo_item")
        col_cantidad = mapeo.get("cantidad")
        col_lote = mapeo.get("numero_lote")
        col_sitio = mapeo.get("codigo_sitio")
        col_zona = mapeo.get("codigo_zona")

        filas_normalizadas = []
        for idx, fila in enumerate(filas_crudas, start=2):  # start=2 para reflejar número de fila con cabecera en fila 1
            codigo_ubi = str(fila.get(col_ubicacion)).strip() if col_ubicacion and fila.get(col_ubicacion) is not None else None
            codigo_item = str(fila.get(col_item)).strip() if col_item and fila.get(col_item) is not None else None
            num_lote = str(fila.get(col_lote)).strip() if col_lote and fila.get(col_lote) is not None else None
            codigo_sitio = str(fila.get(col_sitio)).strip() if col_sitio and fila.get(col_sitio) is not None else None
            codigo_zona = str(fila.get(col_zona)).strip() if col_zona and fila.get(col_zona) is not None else None
            aliases = mapeo.get("__equivalencias", {})
            scoped_key = f"{codigo_sitio or ''}|{codigo_zona or ''}|{codigo_ubi or ''}"
            target = aliases.get(scoped_key) or aliases.get(codigo_ubi)
            if target:
                codigo_ubi, codigo_sitio, codigo_zona = (target["codigo_ubicacion"].strip(),
                    target["codigo_sitio"].strip(), target["codigo_zona"].strip())

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
                "codigo_sitio": codigo_sitio,
                "codigo_zona": codigo_zona,
                "codigo_item": codigo_item,
                "numero_lote": num_lote,
                "cantidad": cantidad,
                "datos_crudos": fila,
            })

        return filas_normalizadas
