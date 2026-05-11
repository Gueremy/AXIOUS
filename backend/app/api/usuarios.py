from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models.usuario import Usuario, UsuarioGalpon
from app.models.sede import Sede
from app.models.galpon import Galpon
from app.schemas.usuario import UsuarioRead, UsuarioUpdate
from app.schemas.common import PaginatedResponse
from app.core.dependencies import get_current_user, require_role
from app.core.audit import log_action
from app.core.logger import log_usuario_desactivado

router = APIRouter()

@router.get("/", response_model=PaginatedResponse[UsuarioRead])
async def read_usuarios(
    id_sede: str | None = None,
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: Usuario = Depends(require_role(["super_admin", "gerencia", "admin_sede"]))
) -> Any:
    stmt = select(Usuario)

    sede_filter = id_sede
    if current_user.rol == "admin_sede":
        sede_filter = current_user.id_sede

    if sede_filter:
        stmt = stmt.where(Usuario.id_sede == sede_filter)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await db.scalar(count_stmt) or 0

    result = await db.execute(stmt.offset(skip).limit(limit))
    usuarios = result.scalars().all()
    
    return {
        "items": usuarios,
        "total": total,
        "page": (skip // limit) + 1 if limit > 0 else 1,
        "size": limit,
        "pages": (total + limit - 1) // limit if limit > 0 else 1
    }

@router.patch("/{id}", response_model=UsuarioRead)
async def update_usuario(
    id: str,
    usuario_in: UsuarioUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role(["super_admin", "admin_sede"]))
) -> Any:
    stmt = select(Usuario).where(Usuario.id == id)
    usuario = (await db.execute(stmt)).scalars().first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if current_user.rol == "admin_sede" and usuario.id_sede != current_user.id_sede:
        raise HTTPException(status_code=403, detail="No tienes permisos sobre este operario")

    update_data = usuario_in.model_dump(exclude_unset=True)
    if "password" in update_data:
        del update_data["password"] # No cambiar la password por acá

    for field, value in update_data.items():
        setattr(usuario, field, value)
    
    await log_action(db, current_user.id, "ACTUALIZAR_USUARIO", "Usuario", str(usuario.id), update_data)
    await db.commit()
    await db.refresh(usuario)

    if update_data.get("activo") is False:
        log_usuario_desactivado(
            nombre_admin=current_user.nombre,
            nombre_usuario=usuario.nombre,
            email=usuario.email,
        )

    return usuario

@router.post("/{id}/asignar-galpones")
async def asignar_galpones(
    id: str,
    galpones_ids: List[str],
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role(["super_admin", "admin_sede"]))
) -> Any:
    """Asigna galpones específicos a un Jefe de Bodega u Operario"""
    stmt = select(Usuario).where(Usuario.id == id)
    usuario = (await db.execute(stmt)).scalars().first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if current_user.rol == "admin_sede" and usuario.id_sede != current_user.id_sede:
        raise HTTPException(403, detail="El usuario pertenece a otra sede")

    # Limpiar asignaciones anteriores
    await db.execute(UsuarioGalpon.__table__.delete().where(UsuarioGalpon.id_usuario == id))
    
    # Asignar nuevas
    for gid in galpones_ids:
        # Validar galpón
        galpon = (await db.execute(select(Galpon).where(Galpon.id == gid))).scalars().first()
        if not galpon:
            continue
        if current_user.rol == "admin_sede" and galpon.id_sede != current_user.id_sede:
            continue
            
        rel = UsuarioGalpon(id_usuario=id, id_galpon=gid)
        db.add(rel)

    await log_action(db, current_user.id, "ASIGNAR_GALPONES", "Usuario", id, {"galpones_asignados": galpones_ids})
    await db.commit()
    return {"mensaje": "Galpones asignados correctamente"}
