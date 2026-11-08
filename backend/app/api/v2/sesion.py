"""Contexto efectivo de sesión para clientes v2."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies_v2 import TenantContext, get_current_tenant
from app.core.modules.registry import ModuleRegistry
from app.database import get_db
from app.services.v2.configuracion_operativa import leer_configuracion

router = APIRouter(prefix="/sesion", tags=["V2 - Sesión"])


@router.get("/offline")
async def preparar_sesion_offline(
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Paquete completo y autorizado. Nunca contiene contraseñas o RUT de trabajadores."""
    from datetime import datetime, timedelta, timezone
    from fastapi import HTTPException
    from sqlalchemy import select
    from fastapi.encoders import jsonable_encoder
    from app.models.v2 import Sitio, Zona, Ubicacion, Item, Lote, SaldoStock, TipoMovimiento
    from app.api.v2.reglas import listar_reglas
    from app.schemas.v2.sitio import SitioRead
    from app.schemas.v2.zona import ZonaRead
    from app.schemas.v2.ubicacion import UbicacionRead
    from app.schemas.v2.item import ItemRead
    from app.schemas.v2.lote import LoteRead
    from app.schemas.v2.movimiento import SaldoStockRead, TipoMovimientoRead
    from app.schemas.v2.regla_ubicacion import ReglaUbicacionRead
    if not tenant.tiene_permiso("stock:read") or not await ModuleRegistry.is_enabled(db, tenant.id_organizacion, "offline_sync"):
        raise HTTPException(403, detail="La organización o el usuario no tienen habilitada la operación offline")
    async def read(model, schema, conditions):
        rows = (await db.execute(select(model).where(*conditions))).scalars().all()
        return [schema.model_validate(row).model_dump(mode="json") for row in rows]
    scope = [Sitio.id_organizacion == tenant.id_organizacion, Sitio.activo == True]
    if tenant.sitios_permitidos is not None:
        scope.append(Sitio.id.in_(tenant.sitios_permitidos))
    sites = await read(Sitio, SitioRead, scope)
    site_ids = [row["id"] for row in sites]
    zones = await read(Zona, ZonaRead, [Zona.id_organizacion == tenant.id_organizacion, Zona.id_sitio.in_(site_ids)])
    locations = await read(Ubicacion, UbicacionRead, [Ubicacion.id_organizacion == tenant.id_organizacion, Ubicacion.id_zona.in_([row["id"] for row in zones]), Ubicacion.activo == True])
    rules = await listar_reglas(tipo_regla=None, id_ubicacion=None, tenant=tenant, db=db)
    now = datetime.now(timezone.utc)
    return {
        "organization_id": tenant.id_organizacion, "user_id": tenant.usuario.id,
        "prepared_at": now.isoformat(), "offline_until": (now + timedelta(hours=72)).isoformat(),
        "permissions": sorted(tenant.permisos), "sites": sites, "zones": zones, "locations": locations,
        "items": await read(Item, ItemRead, [Item.id_organizacion == tenant.id_organizacion, Item.activo == True]),
        "lots": await read(Lote, LoteRead, [Lote.id_organizacion == tenant.id_organizacion]),
        "balances": await read(SaldoStock, SaldoStockRead, [SaldoStock.id_organizacion == tenant.id_organizacion, SaldoStock.id_ubicacion.in_([row["id"] for row in locations])]),
        "movement_types": await read(TipoMovimiento, TipoMovimientoRead, [TipoMovimiento.id_organizacion == tenant.id_organizacion, TipoMovimiento.activo == True]),
        "rules": jsonable_encoder([ReglaUbicacionRead.model_validate(row) for row in rules]),
    }


@router.get("")
async def obtener_sesion(
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Devuelve tenant, permisos efectivos y módulos activos verificados en servidor."""
    modulos = [
        modulo.id for modulo in ModuleRegistry.get_catalog()
        if await ModuleRegistry.is_enabled(db, tenant.id_organizacion, modulo.id)
    ]
    return {
        "usuario": {"id": tenant.usuario.id, "nombre": tenant.usuario.nombre,
                    "rol": tenant.rol_codigo, "id_sede": tenant.usuario.id_sede},
        "organizacion": {"id": tenant.organizacion.id, "nombre": tenant.organizacion.nombre,
                         "slug": tenant.organizacion.slug},
        "configuracion_operativa": leer_configuracion(tenant.organizacion).model_dump(mode="json"),
        "permisos": sorted(tenant.permisos),
        "modulos_activos": modulos,
    }
