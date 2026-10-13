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
    habilitado_por_defecto: bool = True


MODULOS_CATALOGO: Dict[str, ModuleManifest] = {
    "offline_sync": ModuleManifest(
        id="offline_sync",
        nombre="Sincronización Offline PWA",
        version="0.1.0",
        descripcion="Sincronización transaccional con idempotencia para clientes desconectados.",
        rutas_api="/api/v2/movimientos/sync",
        habilitado_por_defecto=True,
    ),
    "importacion": ModuleManifest(
        id="importacion",
        nombre="Importación y Conciliación ERP/WMS",
        version="0.1.0",
        descripcion="Motor de ingesta de CSV/Excel y detección de inconsistencias de stock.",
        rutas_api="/api/v2/importacion",
        habilitado_por_defecto=True,
    ),
    "pack_salmonero": ModuleManifest(
        id="pack_salmonero",
        nombre="Pack Acuícola Salmonero",
        version="0.1.0",
        descripcion="Extensión de validaciones regulatorias SAG/SERNAPESCA y trazabilidad salmonera.",
        eventos_escucha=["movimiento.creado"],
        rutas_api="/api/v2/modulos/salmonero",
        habilitado_por_defecto=False,  # Opcional, núcleo opera limpio si está desactivado
    ),
    "fefo": ModuleManifest(
        id="fefo",
        nombre="Estrategias de Picking Inteligente (FEFO / FIFO / LIFO)",
        version="0.1.0",
        descripcion="Sugerencias de extracción optimizadas por fecha de vencimiento y antigüedad.",
        rutas_api="/api/v2/picking",
        habilitado_por_defecto=True,
    ),
}


class ModuleRegistry:
    _movement_validators: Dict[str, Callable[[Dict[str, Any]], None]] = {}

    @classmethod
    def register_movement_validator(cls, id_modulo: str, validator: Callable[[Dict[str, Any]], None]) -> None:
        cls._movement_validators[id_modulo] = validator

    @classmethod
    async def validate_movement_attributes(cls, db: AsyncSession, id_organizacion: str,
                                           id_modulo: str, atributos: Dict[str, Any]) -> None:
        if await cls.is_enabled(db, id_organizacion, id_modulo):
            validator = cls._movement_validators.get(id_modulo)
            if validator is None:
                raise RuntimeError(f"Validador del módulo '{id_modulo}' no registrado")
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
