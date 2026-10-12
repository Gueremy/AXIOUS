import csv
import io
from typing import Any, Dict, List
from fastapi import HTTPException, status


def parsear_csv(contenido_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Decodifica y procesa contenido de archivo CSV soportando UTF-8 y Latin-1,
    detectando automáticamente separador de comas o punto y coma.
    """
    try:
        texto = contenido_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            texto = contenido_bytes.decode("latin-1")
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No se pudo decodificar el archivo CSV. Asegúrese de que tenga codificación UTF-8 o Latin-1.",
            )

    lineas = texto.splitlines()
    if not lineas:
        return []

    # Detectar delimitador (coma o punto y coma)
    primera_linea = lineas[0]
    delimitador = ";" if primera_linea.count(";") > primera_linea.count(",") else ","

    reader = csv.DictReader(lineas, delimiter=delimitador)
    filas = []
    for fila in reader:
        # Limpiar espacios en blanco de las claves y valores
        fila_limpia = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in fila.items() if k is not None}
        filas.append(fila_limpia)

    return filas
