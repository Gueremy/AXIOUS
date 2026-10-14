"""
app/core/modules/registry.py
Catálogo central de módulos y feature flags por organización (Fase 2C).
Permite activar/desactivar módulos por tenant y verificar disponibilidad.
"""
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends, HTTPException, status

from app.core.dependencies_v2 import TenantContext, get_current_tenant
from app.database import get_db
from app.models.v2.modulo import ModuloOrganizacion


@dataclass
class ModuleManifest:
    id: str
    nombre: str
    version: str
    descripcion: str
    depende_de: List[str] = field(default_factory=lambda: ["core"])
    permisos: List[str] = field(default_factory=list)
    eventos_emite: List[str] = field(default_factory=list)
    eventos_escucha: List[str] = field(default_factory=list)
    rutas_api: str = ""
    tablas: List[str] = field(default_factory=list)
    pantallas: List[str] = field(default_factory=list)
    habilitado_por_defecto: bool = True


MODULOS_CATALOGO: Dict[str, ModuleManifest] = {
    "offline_sync": ModuleManifest(
        id="offline_sync",
        nombre="Sincronización Offline PWA",
        version="0.1.0",
        descripcion="Sincronización transaccional con idempotencia para clientes desconectados.",
        permisos=["movimiento:create"],
        rutas_api="/api/v2/movimientos/sync",
        tablas=["v2_solicitud_movimiento"],
        pantallas=["ColaMovimientos"],
        habilitado_por_defecto=True,
    ),
    "importacion": ModuleManifest(
        id="importacion",
        nombre="Importación y Conciliación ERP/WMS",
        version="0.1.0",
        descripcion="Motor de ingesta de CSV/Excel/API y detección de inconsistencias de stock.",
        permisos=["reporte:export"],
        rutas_api="/api/v2/importacion",
        tablas=["v2_mapping_profile", "v2_importacion_job", "v2_inconsistencia"],
        pantallas=["Importacion", "Conciliacion"],
        eventos_emite=["importacion.finalizada"],
        habilitado_por_defecto=True,
    ),
    "pack_salmonero": ModuleManifest(
        id="pack_salmonero",
        nombre="Pack Acuícola Salmonero",
        version="0.1.0",
        descripcion="Extensión de validaciones regulatorias SAG/SERNAPESCA y trazabilidad salmonera.",
        permisos=["rbac:manage"],
        eventos_escucha=["movimiento.creado"],
        rutas_api="/api/v2/modulos/salmonero",
        pantallas=["ValidacionSalmonera"],
        habilitado_por_defecto=False,  # Opcional, núcleo opera limpio si está desactivado
    ),
    "fefo": ModuleManifest(
        id="fefo",
        nombre="Estrategias de Picking Inteligente (FEFO / FIFO / LIFO)",
        version="0.1.0",
        descripcion="Sugerencias de extracción optimizadas por fecha de vencimiento y antigüedad.",
        permisos=["stock:read"],
        rutas_api="/api/v2/picking",
        pantallas=["SugerenciasPicking"],
        habilitado_por_defecto=True,
    ),
    "demo": ModuleManifest(
        id="demo", nombre="Datos ficticios por industria", version="0.1.0",
        descripcion="Generador de datasets ficticios para demostraciones.",
        permisos=["rbac:manage"], rutas_api="/api/v2/demo",
        pantallas=["GeneradorDemo"], habilitado_por_defecto=True,
    ),
}


class ModuleRegistry:
    _movement_validators: Dict[str, Callable[[Dict[str, Any]], None]] = {}
    _report_handlers: Dict[str, Callable] = {}

    @classmethod
    def register_report_handler(cls, id_modulo: str, handler: Callable) -> None:
        cls._report_handlers[id_modulo] = handler

    @classmethod
    async def collect_report(cls, db: AsyncSession, tenant: TenantContext,
                             kind: str, **kwargs):
        resultados = []
        for id_modulo, handler in cls._report_handlers.items():
            if await cls.is_enabled(db, tenant.id_organizacion, id_modulo):
                value = await handler(db, tenant, kind, **kwargs)
                if value is not None:
                    resultados.append(value)
        if kind.endswith("_count"):
            return sum(resultados)
        if kind.startswith("export_"):
            return resultados[0] if resultados else None
        return [item for resultado in resultados for item in resultado]

    @classmethod
    def register_movement_validator(cls, id_modulo: str, validator: Callable[[Dict[str, Any]], None]) -> None:
        cls._movement_validators[id_modulo] = validator

    @classmethod
    async def validate_movement_attributes(cls, db: AsyncSession, id_organizacion: str,
                                           atributos: Dict[str, Any]) -> None:
        for id_modulo, validator in cls._movement_validators.items():
            if await cls.is_enabled(db, id_organizacion, id_modulo):
                validator(atributos)

    @staticmethod
    def get_catalog() -> List[ModuleManifest]:
        """Retorna todos los módulos registrados en el sistema."""
        return list(MODULOS_CATALOGO.values())

    @staticmethod
    async def is_enabled(db: AsyncSession, id_organizacion: str, id_modulo: str) -> bool:
        """Comprueba si un módulo específico está habilitado para la organización dada."""
        manifest = MODULOS_CATALOGO.get(id_modulo)
        if not manifest:
            return False

        stmt = select(ModuloOrganizacion).where(
            ModuloOrganizacion.id_organizacion == id_organizacion,
            ModuloOrganizacion.id_modulo == id_modulo,
        )
        mod_org = (await db.execute(stmt)).scalar_one_or_none()
        if mod_org is not None:
            return mod_org.habilitado
        return manifest.habilitado_por_defecto

    @staticmethod
    async def set_module_status(
        db: AsyncSession,
        id_organizacion: str,
        id_modulo: str,
        habilitado: bool,
        configuracion: Optional[Dict[str, Any]] = None,
    ) -> ModuloOrganizacion:
        """Activa o desactiva un módulo para una organización."""
        if id_modulo not in MODULOS_CATALOGO:
            raise ValueError(f"Módulo '{id_modulo}' no existe en el catálogo")

        stmt = select(ModuloOrganizacion).where(
            ModuloOrganizacion.id_organizacion == id_organizacion,
            ModuloOrganizacion.id_modulo == id_modulo,
        )
        mod_org = (await db.execute(stmt)).scalar_one_or_none()
        if not mod_org:
            mod_org = ModuloOrganizacion(
                id_organizacion=id_organizacion,
                id_modulo=id_modulo,
                habilitado=habilitado,
                configuracion=configuracion or {},
            )
            db.add(mod_org)
        else:
            mod_org.habilitado = habilitado
            if configuracion is not None:
                mod_org.configuracion = configuracion

        await db.commit()
        await db.refresh(mod_org)
        return mod_org


def require_module_enabled(id_modulo: str):
    """Bloquea una ruta cuando el módulo está apagado para el tenant actual."""
    async def check(
        tenant: TenantContext = Depends(get_current_tenant),
        db: AsyncSession = Depends(get_db),
    ) -> None:
        if not await ModuleRegistry.is_enabled(db, tenant.id_organizacion, id_modulo):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Módulo '{id_modulo}' deshabilitado")
    return check
