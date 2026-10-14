import math
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies_v2 import TenantContext, get_current_tenant
from app.core.validators.schema_validator import validar_atributos, validar_atributos_entidad
from app.database import get_db
from app.models.v2.esquema_atributos import EsquemaAtributos
from app.models.v2.ubicacion import Ubicacion
from app.models.v2.zona import Zona
from app.schemas.v2.common import PaginatedResponse
from app.schemas.v2.ubicacion import UbicacionCreate, UbicacionRead, UbicacionUpdate
from app.services.v2.configuracion_operativa import obtener_configuracion, convertir_cantidad

router = APIRouter(prefix="/ubicaciones", tags=["V2 - Ubicaciones"])


@router.get("/", response_model=PaginatedResponse[UbicacionRead])
async def listar_ubicaciones(
    id_zona: Optional[str] = Query(None, description="Filtrar por zona"),
    estado: Optional[str] = Query(None, description="Filtrar por estado"),
    activo: Optional[bool] = Query(None, description="Filtrar por estado activo"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Lista ubicaciones físicas de almacenamiento pertenecientes a la organización."""
    if not tenant.tiene_permiso("ubicacion:read"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente")

    stmt = select(Ubicacion).where(Ubicacion.id_organizacion == tenant.id_organizacion)
    if tenant.sitios_permitidos is not None:
        stmt = stmt.join(Zona, Ubicacion.id_zona == Zona.id).where(Zona.id_sitio.in_(tenant.sitios_permitidos))
    if id_zona:
        stmt = stmt.where(Ubicacion.id_zona == id_zona)
    if estado:
        stmt = stmt.where(Ubicacion.estado == estado)
    if activo is not None:
        stmt = stmt.where(Ubicacion.activo == activo)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = stmt.order_by(Ubicacion.codigo.asc()).offset((page - 1) * size).limit(size)
    res = await db.execute(stmt)
    ubicaciones = res.scalars().all()

    pages = math.ceil(total / size) if total > 0 else 1
    return PaginatedResponse(items=ubicaciones, total=total, page=page, size=size, pages=pages)


@router.post("/", response_model=UbicacionRead, status_code=status.HTTP_201_CREATED)
async def crear_ubicacion(
    data: UbicacionCreate,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Crea una nueva ubicación de almacenamiento."""
    if not tenant.tiene_permiso("ubicacion:write"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente")

    # 1. Validar que la zona pertenece a la organización
    stmt_zona = select(Zona).where(Zona.id == data.id_zona, Zona.id_organizacion == tenant.id_organizacion)
    zona = (await db.execute(stmt_zona)).scalar_one_or_none()
    if not zona:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zona no encontrada o ajena a la organización")
    tenant.exigir_acceso_sitio(zona.id_sitio)

    # 2. Validar unicidad de código en la zona
    stmt_dup = select(Ubicacion).where(Ubicacion.id_zona == data.id_zona, Ubicacion.codigo == data.codigo)
    dup = (await db.execute(stmt_dup)).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Código de ubicación '{data.codigo}' ya existe en esta zona")

    # 3. Validar atributos contra esquema si existe
    stmt_esq = select(EsquemaAtributos).where(
        EsquemaAtributos.id_organizacion == tenant.id_organizacion,
        EsquemaAtributos.entidad == "ubicacion",
        EsquemaAtributos.activo == True,
    ).order_by(EsquemaAtributos.version.desc())
    esq = (await db.execute(stmt_esq)).scalars().first()
    if esq and esq.schema_json:
        validar_atributos(data.atributos, esq.schema_json)

    ubi = Ubicacion(
        id_organizacion=tenant.id_organizacion,
        id_zona=data.id_zona,
        codigo=data.codigo,
        capacidad_maxima=data.capacidad_maxima,
        unidad_capacidad=data.unidad_capacidad,
        ocupacion_actual=0.0,
        permite_mezcla_lotes=data.permite_mezcla_lotes,
        estado=data.estado,
        layout=data.layout,
        atributos=data.atributos,
        activo=True,
    )
    db.add(ubi)
    await db.commit()
    await db.refresh(ubi)
    return ubi


@router.get("/{id_ubicacion}", response_model=UbicacionRead)
async def obtener_ubicacion(
    id_ubicacion: str,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Obtiene una ubicación por ID validando pertenencia a la organización."""
    if not tenant.tiene_permiso("ubicacion:read"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente")

    stmt = select(Ubicacion).where(Ubicacion.id == id_ubicacion, Ubicacion.id_organizacion == tenant.id_organizacion)
    ubi = (await db.execute(stmt)).scalar_one_or_none()
    if not ubi:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ubicación no encontrada")
    if tenant.sitios_permitidos is not None:
        from app.core.site_access import require_zone_access
        await require_zone_access(db, tenant, ubi.id_zona)
    return ubi


@router.patch("/{id_ubicacion}", response_model=UbicacionRead)
async def actualizar_ubicacion(
    id_ubicacion: str,
    data: UbicacionUpdate,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Actualiza atributos, capacidad o estado de una ubicación."""
    if not tenant.tiene_permiso("ubicacion:write"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente")

    stmt = select(Ubicacion).where(Ubicacion.id == id_ubicacion, Ubicacion.id_organizacion == tenant.id_organizacion)
    ubi = (await db.execute(stmt)).scalar_one_or_none()
    if not ubi:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ubicación no encontrada")
    if tenant.sitios_permitidos is not None:
        from app.core.site_access import require_zone_access
        await require_zone_access(db, tenant, ubi.id_zona)

    update_dict = data.model_dump(exclude_unset=True)
    nueva_unidad = update_dict.get("unidad_capacidad", ubi.unidad_capacidad)
    if nueva_unidad != ubi.unidad_capacidad:
        config = await obtener_configuracion(db, tenant.id_organizacion)
        ocupacion_convertida = convertir_cantidad(
            ubi.ocupacion_actual, ubi.unidad_capacidad, nueva_unidad, config,
        )
        if "capacidad_maxima" not in update_dict:
            update_dict["capacidad_maxima"] = convertir_cantidad(
                ubi.capacidad_maxima, ubi.unidad_capacidad, nueva_unidad, config,
            )
        ubi.ocupacion_actual = ocupacion_convertida
    if update_dict.get("capacidad_maxima", ubi.capacidad_maxima) < ubi.ocupacion_actual:
        raise HTTPException(status_code=400, detail="La capacidad no puede ser menor a la ocupación actual")
    if "atributos" in update_dict:
        update_dict["atributos"] = update_dict["atributos"] or {}
        await validar_atributos_entidad(db, tenant.id_organizacion, "ubicacion", update_dict["atributos"])
    for field, val in update_dict.items():
        setattr(ubi, field, val)

    await db.commit()
    await db.refresh(ubi)
    return ubi
