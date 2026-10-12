"""
app/core/validators/schema_validator.py
Validador de atributos dinámicos JSONB según esquemas versionados (JSON Schema).
Garantiza que cualquier metadata personalizada cumpla con el contrato definido para la organización.
"""
from typing import Any, Dict, List, Optional
import jsonschema
from jsonschema.exceptions import ValidationError


class AtributosValidationError(ValueError):
    """Excepción lanzada cuando los atributos JSONB no cumplen con el esquema requerido."""

    def __init__(self, message: str, errors: Optional[List[Dict[str, Any]]] = None):
        super().__init__(message)
        self.message = message
        self.errors = errors or []


def validar_atributos(atributos: Dict[str, Any], schema_json: Dict[str, Any]) -> None:
    """
    Valida un diccionario de atributos contra una definición JSON Schema.
    Lanza AtributosValidationError si no cumple el esquema.
    """
    if not schema_json:
        return

    validator = jsonschema.Draft7Validator(schema_json)
    errors = []

    for err in validator.iter_errors(atributos or {}):
        path = ".".join(str(p) for p in err.path) if err.path else "root"
        errors.append({
            "campo": path,
            "mensaje": err.message,
            "regla": err.validator,
        })

    if errors:
        msg = f"Validación de atributos fallida: {errors[0]['mensaje']} en '{errors[0]['campo']}'"
        raise AtributosValidationError(msg, errors=errors)
