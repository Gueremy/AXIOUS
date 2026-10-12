import math
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies_v2 import TenantContext, get_current_tenant
from app.core.validators.schema_validator import validar_atributos
from app.database import get_db
from app.models.v2.esquema_atributos import EsquemaAtributos
from app.models.v2.item import Item
from app.models.v2.lote import Lote
from app.schemas.v2.common import PaginatedResponse
from app.schemas.v2.lote import LoteCreate, LoteRead, LoteUpdate

router = APIRouter(prefix="/lotes", tags=["V2 - Lotes"])


@router.get("/", response_model=PaginatedResponse[LoteRead])
async def listar_lotes(
    id_item: Optional[str] = Query(None, description="Filtrar por ítem"),
    estado: Optional[str] = Query(None, description="Filtrar por estado del lote"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Lista lotes de producción/recepción pertenecientes a la organización."""
    if not tenant.tiene_permiso("lote:read"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente")

    stmt = select(Lote).where(Lote.id_organizacion == tenant.id_organizacion)
    if id_item:
        stmt = stmt.where(Lote.id_item == id_item)
    if estado:
        stmt = stmt.where(Lote.estado == estado)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = stmt.order_by(Lote.fecha_creacion.desc()).offset((page - 1) * size).limit(size)
    res = await db.execute(stmt)
    lotes = res.scalars().all()

    pages = math.ceil(total / size) if total > 0 else 1
    return PaginatedResponse(items=lotes, total=total, page=page, size=size, pages=pages)


@router.post("/", response_model=LoteRead, status_code=status.HTTP_201_CREATED)
async def crear_lote(
    data: LoteCreate,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Crea un nuevo lote para un ítem de la organización."""
    if not tenant.tiene_permiso("lote:write"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente")

    # 1. Validar que el ítem pertenece a la organización
    stmt_item = select(Item).where(Item.id == data.id_item, Item.id_organizacion == tenant.id_organizacion)
    item = (await db.execute(stmt_item)).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ítem no encontrado o ajeno a la organización")

    # 2. Validar unicidad de número de lote por ítem
    stmt_dup = select(Lote).where(Lote.id_item == data.id_item, Lote.numero_lote == data.numero_lote)
    dup = (await db.execute(stmt_dup)).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Número de lote '{data.numero_lote}' ya existe para este ítem")

    # 3. Validar atributos contra esquema si existe
    stmt_esq = select(EsquemaAtributos).where(
        EsquemaAtributos.id_organizacion == tenant.id_organizacion,
        EsquemaAtributos.entidad == "lote",
        EsquemaAtributos.activo == True,
    ).order_by(EsquemaAtributos.version.desc())
    esq = (await db.execute(stmt_esq)).scalars().first()
    if esq and esq.schema_json:
        validar_atributos(data.atributos, esq.schema_json)

    lote = Lote(
        id_organizacion=tenant.id_organizacion,
        id_item=data.id_item,
        numero_lote=data.numero_lote,
        fecha_fabricacion=data.fecha_fabricacion,
        fecha_vencimiento=data.fecha_vencimiento,
        atributos=data.atributos,
        estado=data.estado,
    )
    db.add(lote)
    await db.commit()
    await db.refresh(lote)
    return lote


@router.get("/{id_lote}", response_model=LoteRead)
async def obtener_lote(
    id_lote: str,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Obtiene un lote por ID validando pertenencia a la organización."""
    if not tenant.tiene_permiso("lote:read"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente")

    stmt = select(Lote).where(Lote.id == id_lote, Lote.id_organizacion == tenant.id_organizacion)
    lote = (await db.execute(stmt)).scalar_one_or_none()
    if not lote:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lote no encontrado")
    return lote


@router.patch("/{id_lote}", response_model=LoteRead)
async def actualizar_lote(
    id_lote: str,
    data: LoteUpdate,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Actualiza atributos, fechas o estado de un lote."""
    if not tenant.tiene_permiso("lote:write"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente")

    stmt = select(Lote).where(Lote.id == id_lote, Lote.id_organizacion == tenant.id_organizacion)
    lote = (await db.execute(stmt)).scalar_one_or_none()
    if not lote:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lote no encontrado")

    update_dict = data.model_dump(exclude_unset=True)
    for field, val in update_dict.items():
        setattr(lote, field, val)

    await db.commit()
    await db.refresh(lote)
    return lote
