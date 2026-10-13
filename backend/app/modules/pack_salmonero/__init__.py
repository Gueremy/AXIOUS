from app.modules.pack_salmonero.router import router
from app.modules.pack_salmonero.validator import validar_atributos_salmoneros
from app.core.modules.registry import ModuleRegistry

ModuleRegistry.register_movement_validator("pack_salmonero", validar_atributos_salmoneros)

__all__ = ["router"]
