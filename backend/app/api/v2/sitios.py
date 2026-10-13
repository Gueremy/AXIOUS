import math
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies_v2 import TenantContext, get_current_tenant
from app.core.validators.schema_validator import validar_atributos
from app.database import get_db
from app.models.v2.esquema_atributos import EsquemaAtributos
from app.models.v2.sitio import Sitio
from app.schemas.v2.common import PaginatedResponse
from app.schemas.v2.sitio import SitioCreate, SitioRead, SitioUpdate

router = APIRouter(prefix="/sitios", tags=["V2 - Sitios"])


@router.get("/", response_model=PaginatedResponse[SitioRead])
async def listar_sitios(
    tipo: Optional[str] = Query(None, description="Filtrar por tipo de sitio"),
    activo: Optional[bool] = Query(None, description="Filtrar por estado activo"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Lista sitios pertenecientes a la organización del usuario con paginación."""
    if not tenant.tiene_permiso("sitio:read"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente")

    stmt = select(Sitio).where(Sitio.id_organizacion == tenant.id_organizacion)
    if tenant.sitios_permitidos is not None:
        stmt = stmt.where(Sitio.id.in_(tenant.sitios_permitidos))
    if tipo:
        stmt = stmt.where(Sitio.tipo == tipo)
    if activo is not None:
        stmt = stmt.where(Sitio.activo == activo)

    # Conteo total real
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = stmt.order_by(Sitio.fecha_creacion.desc()).offset((page - 1) * size).limit(size)
    res = await db.execute(stmt)
    sitios = res.scalars().all()

    pages = math.ceil(total / size) if total > 0 else 1
    return PaginatedResponse(items=sitios, total=total, page=page, size=size, pages=pages)


@router.post("/", response_model=SitioRead, status_code=status.HTTP_201_CREATED)
async def crear_sitio(
    data: SitioCreate,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Crea un nuevo sitio dentro de la organización autenticada."""
    if not tenant.tiene_permiso("sitio:write"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente")

    # Validar unicidad de código dentro de la organización
    stmt_dup = select(Sitio).where(
        Sitio.id_organizacion == tenant.id_organizacion,
        Sitio.codigo == data.codigo,
    )
    dup = (await db.execute(stmt_dup)).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Código de sitio '{data.codigo}' ya existe en su organización")

    # Validar atributos contra esquema si está definido
    stmt_esq = select(EsquemaAtributos).where(
        EsquemaAtributos.id_organizacion == tenant.id_organizacion,
        EsquemaAtributos.entidad == "sitio",
        EsquemaAtributos.activo == True,
    ).order_by(EsquemaAtributos.version.desc())
    esq = (await db.execute(stmt_esq)).scalars().first()
    if esq and esq.schema_json:
        validar_atributos(data.atributos, esq.schema_json)

    sitio = Sitio(
        id_organizacion=tenant.id_organizacion,
        codigo=data.codigo,
        nombre=data.nombre,
        tipo=data.tipo,
        descripcion=data.descripcion,
        ubicacion_geografica=data.ubicacion_geografica,
        atributos=data.atributos,
        activo=True,
    )
    db.add(sitio)
    await db.commit()
    await db.refresh(sitio)
    return sitio


@router.get("/{id_sitio}", response_model=SitioRead)
async def obtener_sitio(
    id_sitio: str,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Obtiene el detalle de un sitio específico validando aislamiento de organización."""
    if not tenant.tiene_permiso("sitio:read"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente")

    stmt = select(Sitio).where(Sitio.id == id_sitio, Sitio.id_organizacion == tenant.id_organizacion)
    sitio = (await db.execute(stmt)).scalar_one_or_none()
    if not sitio:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sitio no encontrado")

    if not tenant.puede_acceder_sitio(sitio.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tiene asignado acceso a este sitio")

    return sitio


@router.patch("/{id_sitio}", response_model=SitioRead)
async def actualizar_sitio(
    id_sitio: str,
    data: SitioUpdate,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Actualiza atributos o desactiva un sitio."""
    if not tenant.tiene_permiso("sitio:write"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente")

    stmt = select(Sitio).where(Sitio.id == id_sitio, Sitio.id_organizacion == tenant.id_organizacion)
    sitio = (await db.execute(stmt)).scalar_one_or_none()
    if not sitio:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sitio no encontrado")
    tenant.exigir_acceso_sitio(sitio.id)

    update_dict = data.model_dump(exclude_unset=True)
    if "atributos" in update_dict and update_dict["atributos"] is not None:
        stmt_esq = select(EsquemaAtributos).where(
            EsquemaAtributos.id_organizacion == tenant.id_organizacion,
            EsquemaAtributos.entidad == "sitio",
            EsquemaAtributos.activo == True,
        ).order_by(EsquemaAtributos.version.desc())
        esq = (await db.execute(stmt_esq)).scalars().first()
        if esq and esq.schema_json:
            validar_atributos(update_dict["atributos"], esq.schema_json)

    for field, val in update_dict.items():
        setattr(sitio, field, val)

    await db.commit()
    await db.refresh(sitio)
    return sitio
