from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.sede import Sede
from app.models.usuario import Usuario
from app.schemas.sede import SedeCreate, SedeRead, SedeUpdate
from app.schemas.common import PaginatedResponse
from app.core.dependencies import get_current_user, require_role
from app.core.audit import log_action

router = APIRouter()

@router.get("/", response_model=PaginatedResponse[SedeRead])
async def read_sedes(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: Usuario = Depends(get_current_user)
) -> Any:
    # Contar total
    total = len((await db.execute(select(Sede.id))).all())
    
    stmt = select(Sede).offset(skip).limit(limit)
    # Aislamiento: si no es admin/gerente, solo ve su propia sede
    if current_user.rol not in ["super_admin", "gerencia"] and current_user.id_sede:
        stmt = stmt.where(Sede.id == current_user.id_sede)

    result = await db.execute(stmt)
    sedes = result.scalars().all()
    
    return {
        "items": sedes,
        "total": total,
        "page": (skip // limit) + 1 if limit > 0 else 1,
        "size": limit,
        "pages": (total + limit - 1) // limit if limit > 0 else 1
    }

@router.post("/", response_model=SedeRead, status_code=status.HTTP_201_CREATED)
async def create_sede(
    sede_in: SedeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role(["super_admin"]))
) -> Any:
    sede = Sede(**sede_in.model_dump())
    db.add(sede)
    await db.commit()
    await db.refresh(sede)
    
    await log_action(db, current_user.id, "CREAR_SEDE", "Sede", str(sede.id), sede_in.model_dump())
    await db.commit()
    return sede

@router.get("/{id}", response_model=SedeRead)
async def read_sede(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
) -> Any:
    if current_user.rol not in ["super_admin", "gerencia"] and current_user.id_sede != id:
        raise HTTPException(status_code=403, detail="No tienes permisos para ver esta sede")

    stmt = select(Sede).where(Sede.id == id)
    result = await db.execute(stmt)
    sede = result.scalars().first()
    if not sede:
        raise HTTPException(status_code=404, detail="Sede no encontrada")
    return sede

@router.patch("/{id}", response_model=SedeRead)
async def update_sede(
    id: str,
    sede_in: SedeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role(["super_admin"]))
) -> Any:
    stmt = select(Sede).where(Sede.id == id)
    result = await db.execute(stmt)
    sede = result.scalars().first()
    if not sede:
        raise HTTPException(status_code=404, detail="Sede no encontrada")

    update_data = sede_in.model_dump(exclude_unset=True)
    if not update_data:
        return sede

    for field, value in update_data.items():
        setattr(sede, field, value)
    
    await log_action(db, current_user.id, "ACTUALIZAR_SEDE", "Sede", str(sede.id), update_data)
    await db.commit()
    await db.refresh(sede)
    return sede

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sede(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role(["super_admin"]))
):
    stmt = select(Sede).where(Sede.id == id)
    result = await db.execute(stmt)
    sede = result.scalars().first()
    if not sede:
        raise HTTPException(status_code=404, detail="Sede no encontrada")
    
    # Soft delete (Desactivación)
    sede.estado = "inactivo"
    await log_action(db, current_user.id, "DESACTIVAR_SEDE", "Sede", str(sede.id), {"estado": "inactivo"})
    await db.commit()
    return None
