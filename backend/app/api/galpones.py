from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.galpon import Galpon
from app.models.sede import Sede
from app.models.usuario import Usuario
from app.schemas.galpon import GalponCreate, GalponRead, GalponUpdate
from app.schemas.common import PaginatedResponse
from app.core.dependencies import get_current_user, require_role
from app.core.audit import log_action

router = APIRouter()

@router.get("/", response_model=PaginatedResponse[GalponRead])
async def read_galpones(
    id_sede: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: Usuario = Depends(get_current_user)
) -> Any:
    # Aislamiento Tenant
    sede_filter = id_sede
    if current_user.rol not in ["super_admin", "gerencia"]:
        sede_filter = current_user.id_sede

    stmt = select(Galpon)
    if sede_filter:
        stmt = stmt.where(Galpon.id_sede == sede_filter)

    # Contar total rápido
    total_result = await db.execute(stmt)
    total = len(total_result.scalars().all())

    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    galpones = result.scalars().all()
    
    return {
        "items": galpones,
        "total": total,
        "page": (skip // limit) + 1 if limit > 0 else 1,
        "size": limit,
        "pages": (total + limit - 1) // limit if limit > 0 else 1
    }

@router.post("/", response_model=GalponRead, status_code=status.HTTP_201_CREATED)
async def create_galpon(
    galpon_in: GalponCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role(["super_admin", "admin_sede"]))
) -> Any:
    # Validar permisos si es admin_sede
    if current_user.rol == "admin_sede" and galpon_in.id_sede != current_user.id_sede:
        raise HTTPException(status_code=403, detail="No puedes crear galpones en otra sede")

    # Validar existencia de sede
    sede = (await db.execute(select(Sede).where(Sede.id == galpon_in.id_sede))).scalars().first()
    if not sede:
        raise HTTPException(status_code=404, detail="Sede no encontrada")

    # Validar codigo único por sede
    codigo_existente = (await db.execute(
        select(Galpon).where(Galpon.codigo == galpon_in.codigo, Galpon.id_sede == galpon_in.id_sede)
    )).scalars().first()
    if codigo_existente:
        raise HTTPException(status_code=400, detail="El código de galpón ya existe en esta sede")

    galpon = Galpon(**galpon_in.model_dump())
    db.add(galpon)
    await db.commit()
    await db.refresh(galpon)
    
    await log_action(db, current_user.id, "CREAR_GALPON", "Galpon", str(galpon.id), galpon_in.model_dump())
    await db.commit()
    return galpon

@router.get("/{id}", response_model=GalponRead)
async def read_galpon(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
) -> Any:
    stmt = select(Galpon).where(Galpon.id == id)
    result = await db.execute(stmt)
    galpon = result.scalars().first()
    
    if not galpon:
        raise HTTPException(status_code=404, detail="Galpón no encontrado")
        
    if current_user.rol not in ["super_admin", "gerencia"] and current_user.id_sede != galpon.id_sede:
        raise HTTPException(status_code=403, detail="No tienes permisos para ver este galpón")

    return galpon

@router.patch("/{id}", response_model=GalponRead)
async def update_galpon(
    id: str,
    galpon_in: GalponUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role(["super_admin", "admin_sede"]))
) -> Any:
    stmt = select(Galpon).where(Galpon.id == id)
    result = await db.execute(stmt)
    galpon = result.scalars().first()
    if not galpon:
        raise HTTPException(status_code=404, detail="Galpón no encontrado")

    if current_user.rol == "admin_sede" and galpon.id_sede != current_user.id_sede:
        raise HTTPException(status_code=403, detail="No puedes modificar galpones de otra sede")

    update_data = galpon_in.model_dump(exclude_unset=True)
    if not update_data:
        return galpon

    # Si intenta cambiar id_sede
    if "id_sede" in update_data and current_user.rol != "super_admin":
        raise HTTPException(status_code=403, detail="Un admin_sede no puede mover un galpón a otra sede")

    for field, value in update_data.items():
        setattr(galpon, field, value)
    
    await log_action(db, current_user.id, "ACTUALIZAR_GALPON", "Galpon", str(galpon.id), update_data)
    await db.commit()
    await db.refresh(galpon)
    return galpon
