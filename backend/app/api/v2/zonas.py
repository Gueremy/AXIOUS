import math
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies_v2 import TenantContext, get_current_tenant
from app.core.validators.schema_validator import validar_atributos
from app.database import get_db
from app.models.v2.esquema_atributos import EsquemaAtributos
from app.models.v2.sitio import Sitio
from app.models.v2.zona import Zona
from app.schemas.v2.common import PaginatedResponse
from app.schemas.v2.zona import ZonaCreate, ZonaRead, ZonaUpdate

router = APIRouter(prefix="/zonas", tags=["V2 - Zonas"])


@router.get("/", response_model=PaginatedResponse[ZonaRead])
async def listar_zonas(
    id_sitio: Optional[str] = Query(None, description="Filtrar por sitio"),
    id_zona_padre: Optional[str] = Query(None, description="Filtrar por zona padre directa"),
    activo: Optional[bool] = Query(None, description="Filtrar por estado activo"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Lista zonas de la organización autenticada con filtros por sitio y jerarquía."""
    if not tenant.tiene_permiso("zona:read"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente")

    stmt = select(Zona).where(Zona.id_organizacion == tenant.id_organizacion)
    if id_sitio:
        stmt = stmt.where(Zona.id_sitio == id_sitio)
    if id_zona_padre is not None:
        stmt = stmt.where(Zona.id_zona_padre == id_zona_padre)
    if activo is not None:
        stmt = stmt.where(Zona.activo == activo)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = stmt.order_by(Zona.codigo.asc()).offset((page - 1) * size).limit(size)
    res = await db.execute(stmt)
    zonas = res.scalars().all()

    pages = math.ceil(total / size) if total > 0 else 1
    return PaginatedResponse(items=zonas, total=total, page=page, size=size, pages=pages)


@router.post("/", response_model=ZonaRead, status_code=status.HTTP_201_CREATED)
async def crear_zona(
    data: ZonaCreate,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Crea una nueva zona validando pertenencia al sitio y evitando ciclos en la jerarquía."""
    if not tenant.tiene_permiso("zona:write"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente")

    # 1. Validar que el sitio pertenece a la organización
    stmt_sitio = select(Sitio).where(Sitio.id == data.id_sitio, Sitio.id_organizacion == tenant.id_organizacion)
    sitio = (await db.execute(stmt_sitio)).scalar_one_or_none()
    if not sitio:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sitio no encontrado o ajeno a la organización")

    # 2. Si tiene zona padre, validar que pertenezca al mismo sitio
    if data.id_zona_padre:
        stmt_padre = select(Zona).where(Zona.id == data.id_zona_padre, Zona.id_sitio == data.id_sitio)
        padre = (await db.execute(stmt_padre)).scalar_one_or_none()
        if not padre:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="La zona padre no existe o pertenece a otro sitio")

    # 3. Validar unicidad de código en el sitio
    stmt_dup = select(Zona).where(Zona.id_sitio == data.id_sitio, Zona.codigo == data.codigo)
    dup = (await db.execute(stmt_dup)).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Código de zona '{data.codigo}' ya existe en este sitio")

    # 4. Validar atributos contra esquema si existe
    stmt_esq = select(EsquemaAtributos).where(
        EsquemaAtributos.id_organizacion == tenant.id_organizacion,
        EsquemaAtributos.entidad == "zona",
        EsquemaAtributos.activo == True,
    ).order_by(EsquemaAtributos.version.desc())
    esq = (await db.execute(stmt_esq)).scalars().first()
    if esq and esq.schema_json:
        validar_atributos(data.atributos, esq.schema_json)

    zona = Zona(
        id_organizacion=tenant.id_organizacion,
        id_sitio=data.id_sitio,
        id_zona_padre=data.id_zona_padre,
        codigo=data.codigo,
        nombre=data.nombre,
        tipo=data.tipo,
        layout=data.layout,
        atributos=data.atributos,
        activo=True,
    )
    db.add(zona)
    await db.commit()
    await db.refresh(zona)
    return zona


@router.get("/{id_zona}", response_model=ZonaRead)
async def obtener_zona(
    id_zona: str,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Obtiene una zona por ID validando pertenencia a la organización."""
    if not tenant.tiene_permiso("zona:read"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente")

    stmt = select(Zona).where(Zona.id == id_zona, Zona.id_organizacion == tenant.id_organizacion)
    zona = (await db.execute(stmt)).scalar_one_or_none()
    if not zona:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zona no encontrada")
    return zona


@router.get("/{id_zona}/hijos", response_model=List[ZonaRead])
async def obtener_subzonas(
    id_zona: str,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Obtiene las subzonas hijas directas de una zona."""
    if not tenant.tiene_permiso("zona:read"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente")

    # Validar que la zona padre pertenece a la organización
    stmt_padre = select(Zona).where(Zona.id == id_zona, Zona.id_organizacion == tenant.id_organizacion)
    padre = (await db.execute(stmt_padre)).scalar_one_or_none()
    if not padre:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zona no encontrada")

    stmt = select(Zona).where(Zona.id_zona_padre == id_zona, Zona.id_organizacion == tenant.id_organizacion).order_by(Zona.codigo.asc())
    res = await db.execute(stmt)
    return res.scalars().all()


@router.patch("/{id_zona}", response_model=ZonaRead)
async def actualizar_zona(
    id_zona: str,
    data: ZonaUpdate,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Actualiza layout, atributos o estado de una zona."""
    if not tenant.tiene_permiso("zona:write"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente")

    stmt = select(Zona).where(Zona.id == id_zona, Zona.id_organizacion == tenant.id_organizacion)
    zona = (await db.execute(stmt)).scalar_one_or_none()
    if not zona:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zona no encontrada")

    update_dict = data.model_dump(exclude_unset=True)
    for field, val in update_dict.items():
        setattr(zona, field, val)

    await db.commit()
    await db.refresh(zona)
    return zona
