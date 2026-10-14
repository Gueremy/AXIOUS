import math
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies_v2 import TenantContext, get_current_tenant
from app.core.validators.schema_validator import validar_atributos, validar_atributos_entidad
from app.database import get_db
from app.models.v2.esquema_atributos import EsquemaAtributos
from app.models.v2.item import Item
from app.models.v2.saldo_stock import SaldoStock
from app.schemas.v2.common import PaginatedResponse
from app.schemas.v2.item import ItemCreate, ItemRead, ItemUpdate

router = APIRouter(prefix="/items", tags=["V2 - Items"])


@router.get("/", response_model=PaginatedResponse[ItemRead])
async def listar_items(
    categoria: Optional[str] = Query(None, description="Filtrar por categoría"),
    activo: Optional[bool] = Query(None, description="Filtrar por estado activo"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Lista catálogo de ítems pertenecientes a la organización."""
    if not tenant.tiene_permiso("item:read"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente")

    stmt = select(Item).where(Item.id_organizacion == tenant.id_organizacion)
    if categoria:
        stmt = stmt.where(Item.categoria == categoria)
    if activo is not None:
        stmt = stmt.where(Item.activo == activo)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = stmt.order_by(Item.codigo.asc()).offset((page - 1) * size).limit(size)
    res = await db.execute(stmt)
    items = res.scalars().all()

    pages = math.ceil(total / size) if total > 0 else 1
    return PaginatedResponse(items=items, total=total, page=page, size=size, pages=pages)


@router.post("/", response_model=ItemRead, status_code=status.HTTP_201_CREATED)
async def crear_item(
    data: ItemCreate,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Crea un nuevo ítem en el catálogo de la organización."""
    if not tenant.tiene_permiso("item:write"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente")

    # 1. Validar unicidad de código dentro de la organización
    stmt_dup = select(Item).where(Item.id_organizacion == tenant.id_organizacion, Item.codigo == data.codigo)
    dup = (await db.execute(stmt_dup)).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Código de ítem '{data.codigo}' ya existe en su organización")

    # 2. Validar atributos contra esquema si existe
    stmt_esq = select(EsquemaAtributos).where(
        EsquemaAtributos.id_organizacion == tenant.id_organizacion,
        EsquemaAtributos.entidad == "item",
        EsquemaAtributos.activo == True,
    ).order_by(EsquemaAtributos.version.desc())
    esq = (await db.execute(stmt_esq)).scalars().first()
    if esq and esq.schema_json:
        validar_atributos(data.atributos, esq.schema_json)

    item = Item(
        id_organizacion=tenant.id_organizacion,
        codigo=data.codigo,
        nombre=data.nombre,
        categoria=data.categoria,
        unidad_medida=data.unidad_medida,
        atributos=data.atributos,
        activo=True,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.get("/{id_item}", response_model=ItemRead)
async def obtener_item(
    id_item: str,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Obtiene un ítem por ID validando pertenencia a la organización."""
    if not tenant.tiene_permiso("item:read"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente")

    stmt = select(Item).where(Item.id == id_item, Item.id_organizacion == tenant.id_organizacion)
    item = (await db.execute(stmt)).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ítem no encontrado")
    return item


@router.patch("/{id_item}", response_model=ItemRead)
async def actualizar_item(
    id_item: str,
    data: ItemUpdate,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Actualiza datos o desactiva un ítem de la organización."""
    if not tenant.tiene_permiso("item:write"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente")

    stmt = select(Item).where(Item.id == id_item, Item.id_organizacion == tenant.id_organizacion)
    item = (await db.execute(stmt)).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ítem no encontrado")

    update_dict = data.model_dump(exclude_unset=True)
    if "unidad_medida" in update_dict and update_dict["unidad_medida"] != item.unidad_medida:
        saldos = (await db.execute(select(func.count(SaldoStock.id)).where(
            SaldoStock.id_item == item.id, SaldoStock.cantidad > 0,
        ))).scalar_one()
        if saldos:
            raise HTTPException(status_code=409, detail="No se puede cambiar la unidad de un ítem con stock")
    if "atributos" in update_dict:
        update_dict["atributos"] = update_dict["atributos"] or {}
        await validar_atributos_entidad(db, tenant.id_organizacion, "item", update_dict["atributos"])
    for field, val in update_dict.items():
        setattr(item, field, val)

    await db.commit()
    await db.refresh(item)
    return item
