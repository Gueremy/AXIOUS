import io
from typing import Any, Dict, List
from fastapi import HTTPException, status
import openpyxl


def parsear_excel(contenido_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Lee archivos Excel (.xlsx) usando openpyxl en modo sólo datos (sin evaluar macros/código activo).
    Trata la primera fila como encabezados de columna.
    """
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(contenido_bytes), data_only=True, read_only=True)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error al abrir el archivo Excel. Verifique que sea un archivo .xlsx válido: {str(exc)}",
        )

    hoja = workbook.active
    filas_iter = hoja.iter_rows(values_only=True)

    try:
        encabezados = next(filas_iter)
    except StopIteration:
        return []

    if not encabezados:
        return []

    # Filtrar encabezados nulos y limpiar strings
    nombres_columna = [str(col).strip() if col is not None else f"col_{idx}" for idx, col in enumerate(encabezados)]

    registros = []
    for fila in filas_iter:
        if not any(celda is not None for celda in fila):
            continue  # ignorar filas vacías

        registro = {}
        for idx, valor in enumerate(fila):
            if idx < len(nombres_columna):
                col_name = nombres_columna[idx]
                registro[col_name] = str(valor).strip() if isinstance(valor, str) else valor
        registros.append(registro)

    workbook.close()
    return registros
