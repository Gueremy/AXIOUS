from app.modules.importacion.models import MappingProfile, ImportacionJob, Inconsistencia
from app.modules.importacion.router import router
from app.modules.importacion.reports import report_provider
from app.core.modules.registry import ModuleRegistry

ModuleRegistry.register_report_handler("importacion", report_provider)

__all__ = ["MappingProfile", "ImportacionJob", "Inconsistencia", "router"]
