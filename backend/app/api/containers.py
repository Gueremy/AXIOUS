import qrcode
import base64
from io import BytesIO
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models.container import Container
from app.models.galpon import Galpon
from app.models.sede import Sede
from app.models.usuario import Usuario
from app.schemas.container import ContainerCreate, ContainerRead, ContainerUpdate
from app.schemas.common import PaginatedResponse
from app.core.dependencies import get_current_user, require_role
from app.core.audit import log_action
from app.core.logger import log_container_creado

router = APIRouter()

@router.get("/", response_model=PaginatedResponse[ContainerRead])
async def read_containers(
    id_galpon: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: Usuario = Depends(get_current_user)
) -> Any:
    stmt = select(Container)
    
    # Si manda galpón, validamos
    if id_galpon:
        stmt = stmt.where(Container.id_galpon == id_galpon)
        
    # Seguridad de Aislamiento Tenant (Cruzar Container -> Galpon -> Sede)
    if current_user.rol not in ["super_admin", "gerencia"]:
        stmt = stmt.join(Galpon, Container.id_galpon == Galpon.id).where(Galpon.id_sede == current_user.id_sede)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await db.scalar(count_stmt)

    result = await db.execute(stmt.offset(skip).limit(limit))
    containers = result.scalars().all()
    
    return {
        "items": containers,
        "total": total,
        "page": (skip // limit) + 1 if limit > 0 else 1,
        "size": limit,
        "pages": (total + limit - 1) // limit if limit > 0 else 1
    }

@router.post("/", response_model=ContainerRead, status_code=status.HTTP_201_CREATED)
async def create_container(
    container_in: ContainerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role(["super_admin", "admin_sede"]))
) -> Any:
    galpon = (await db.execute(select(Galpon).where(Galpon.id == container_in.id_galpon))).scalars().first()
    if not galpon:
        raise HTTPException(status_code=404, detail="Galpón no encontrado")

    if current_user.rol == "admin_sede" and galpon.id_sede != current_user.id_sede:
        raise HTTPException(status_code=403, detail="El galpón pertenece a otra sede")

    # Validar grilla
    if container_in.posicion_fila > galpon.filas or container_in.posicion_col > galpon.columnas:
        raise HTTPException(status_code=400, detail="La posición excede las dimensiones del galpón")

    # Verificar si la posición está ocupada
    ocupado = (await db.execute(
        select(Container).where(
            Container.id_galpon == galpon.id,
            Container.posicion_fila == container_in.posicion_fila,
            Container.posicion_col == container_in.posicion_col
        )
    )).scalars().first()
    
    if ocupado:
        raise HTTPException(status_code=400, detail="Ya existe un container en esta posición Grial")

    container = Container(**container_in.model_dump())
    db.add(container)
    await db.commit()
    await db.refresh(container)

    await log_action(db, current_user.id, "CREAR_CONTAINER", "Container", str(container.id), container_in.model_dump())
    await db.commit()

    sede = (await db.execute(select(Sede).where(Sede.id == galpon.id_sede))).scalars().first()
    log_container_creado(
        nombre_usuario=current_user.nombre,
        codigo=container.codigo,
        galpon_nombre=galpon.nombre,
        sede_nombre=sede.nombre if sede else "Sede desconocida",
        capacidad=float(container.capacidad_max),
        unidad=container.unidad_medida,
    )

    return container

@router.get("/{id}", response_model=ContainerRead)
async def read_container(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
) -> Any:
    stmt = select(Container).where(Container.id == id)
    result = await db.execute(stmt)
    container = result.scalars().first()
    if not container:
        raise HTTPException(status_code=404, detail="Container no encontrado")
        
    return container

@router.patch("/{id}/estado", response_model=ContainerRead)
async def update_container_estado(
    id: str,
    estado: str,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role(["jefe_bodega", "admin_sede", "super_admin"]))
) -> Any:
    """Modifica únicamente el estado del contenedor (Auditable)"""
    stmt = select(Container).where(Container.id == id)
    result = await db.execute(stmt)
    container = result.scalars().first()
    if not container:
        raise HTTPException(status_code=404, detail="Container no encontrado")

    estado_anterior = container.estado
    container.estado = estado
    
    detalle = {
        "estado_anterior": estado_anterior,
        "estado_nuevo": estado
    }
    await log_action(db, current_user.id, "CAMBIO_ESTADO_CONTAINER", "Container", str(container.id), detalle)
    await db.commit()
    await db.refresh(container)
    return container

@router.get("/{id}/qr")
async def get_container_qr(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
) -> Any:
    """Genera un archivo QR en base64 para uso en interfaces 3D / Etiquetas físicas"""
    stmt = select(Container).where(Container.id == id)
    container = (await db.execute(stmt)).scalars().first()
    if not container:
        raise HTTPException(404, "Container no encontrado")

    qr_data = f"app-3d-salmonera://container?id={container.id}"
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(qr_data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    
    return {"qr_base64": img_str, "data_encoded": qr_data}

@router.get("/{id}/info-publica")
async def get_info_publica(
    id: str,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """Endpoint público para escáneres web que no requiere JWT."""
    stmt = select(Container).where(Container.id == id)
    container = (await db.execute(stmt)).scalars().first()
    if not container:
        raise HTTPException(404, "Container no encontrado")
        
    return {
        "codigo": container.codigo,
        "estado": container.estado,
        "ocupacion_actual": container.ocupacion_actual,
        "capacidad_max": container.capacidad_max,
        "unidad_medida": container.unidad_medida,
        "tipo_permitido": container.tipo_producto_permitido
    }
