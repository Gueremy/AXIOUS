from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime

from app.database import get_db
from app.models.movimiento import Movimiento
from app.models.container import Container
from app.models.producto import Producto
from app.models.galpon import Galpon
from app.models.sede import Sede
from app.models.usuario import Usuario
from app.schemas.movimiento import (MovimientoCreate, MovimientoRead, 
                                    MovimientoAprobar, MovimientoRechazar)
from app.core.dependencies import get_current_user, require_role
from app.core.audit import log_action
from app.services.alertas import evaluar_alertas

router = APIRouter()

INCOMPATIBLE = {
    'alimento': ['quimico', 'veterinario'],
    'quimico':  ['alimento', 'veterinario'],
    'veterinario': ['alimento']
}

@router.post("/", response_model=MovimientoRead, status_code=status.HTTP_201_CREATED)
async def create_movimiento(
    mov_in: MovimientoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
) -> Any:
    # 1. Validar container origen
    container = (await db.execute(select(Container).where(Container.id == mov_in.id_container))).scalars().first()
    if not container:
        raise HTTPException(status_code=404, detail="Container no encontrado")

    # 2. Validar producto   
    producto = (await db.execute(select(Producto).where(Producto.id == mov_in.id_producto))).scalars().first()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    # 3. Separación de Entornos (INCOMPATIBLE table)
    if container.tipo_producto_permitido in INCOMPATIBLE:
        if producto.categoria in INCOMPATIBLE[container.tipo_producto_permitido]:
            raise HTTPException(
                status_code=400, 
                detail=f"Incompatibilidad de producto. No se pueden mezclar productos de tipo {producto.categoria} en un container para {container.tipo_producto_permitido}."
            )

    # 4. Validar reglas de SAG (Veterinarios)
    if producto.categoria == "veterinario" and mov_in.tipo == "entrada_proveedor":
        if not mov_in.num_receta_retenida or not mov_in.num_autorizacion_sag:
            raise HTTPException(
                status_code=422,
                detail="Los campos num_receta_retenida y num_autorizacion_sag son MANDATORIOS para medicamentos veterinarios según normativa SAG."
            )

    # Preparar el objeto para Base de Datos
    data_dict = mov_in.model_dump(exclude_unset=True)
    movimiento = Movimiento(**data_dict)
    movimiento.id_usuario = current_user.id
    
    # 5. Flujo dependiendo del tipo
    if mov_in.tipo == "entrada_proveedor":
        if container.ocupacion_actual + mov_in.cantidad > container.capacidad_max:
            raise HTTPException(status_code=400, detail=f"La entrada supera la capacidad máxima ({container.capacidad_max}) del container.")
        movimiento.estado = "pendiente"

    elif mov_in.tipo == "salida_produccion":
        if container.ocupacion_actual < mov_in.cantidad:
            raise HTTPException(status_code=400, detail="Stock insuficiente para este despacho en el container origen.")
        movimiento.estado = "pendiente"

    elif mov_in.tipo == "traslado_interno":
        if not mov_in.id_container_destino:
            raise HTTPException(status_code=400, detail="El container de destino es obligatorio en un traslado interno")
        
        container_dst = (await db.execute(select(Container).where(Container.id == mov_in.id_container_destino))).scalars().first()
        if not container_dst:
            raise HTTPException(status_code=404, detail="Container destino no encontrado")
        
        if container.ocupacion_actual < mov_in.cantidad:
            raise HTTPException(status_code=400, detail="Stock insuficiente para este traslado en el container origen.")
            
        if container_dst.ocupacion_actual + mov_in.cantidad > container_dst.capacidad_max:
            raise HTTPException(status_code=400, detail="El container de destino no tiene capacidad suficiente")

        # Auto-aprobar y hacer matemáticas inmediatamente para Traslados (Operatividad Rápida)
        movimiento.estado = "aprobado"
        movimiento.fecha_aprobacion = datetime.utcnow()
        container.ocupacion_actual -= mov_in.cantidad
        container.fecha_ultimo_movimiento = datetime.utcnow()
        container_dst.ocupacion_actual += mov_in.cantidad
        container_dst.fecha_ultimo_movimiento = datetime.utcnow()
        # Se evalúan alertas más abajo si es necesario
    else:
        # correcciones u otros
        movimiento.estado = "pendiente"

    db.add(movimiento)
    await db.commit()
    await db.refresh(movimiento)
    
    await log_action(db, current_user.id, "REGISTRAR_MOVIMIENTO", "Movimiento", str(movimiento.id), {"tipo": mov_in.tipo, "estado": movimiento.estado})
    
    if mov_in.tipo == "traslado_interno":
        await evaluar_alertas(container.id, db)
        await evaluar_alertas(container_dst.id, db)

    return movimiento


@router.patch("/{id}/aprobar", response_model=MovimientoRead)
async def aprobar_movimiento(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role(["jefe_bodega", "super_admin"]))
) -> Any:
    movimiento = (await db.execute(select(Movimiento).where(Movimiento.id == id))).scalars().first()
    if not movimiento:
        raise HTTPException(status_code=404, detail="Movimiento no encontrado")

    if movimiento.estado != "pendiente":
        raise HTTPException(status_code=400, detail=f"El movimiento ya está {movimiento.estado}")

    # Restricción A04 OWASP: Jefe no aprueba lo suyo
    if movimiento.id_usuario == current_user.id:
        raise HTTPException(status_code=403, detail="Ciberseguridad (A04): No puedes aprobar movimientos que tú mismo generaste.")

    container = (await db.execute(select(Container).where(Container.id == movimiento.id_container))).scalars().first()

    # Impacto matemático según tipo
    if movimiento.tipo == "entrada_proveedor":
        if container.ocupacion_actual + movimiento.cantidad > container.capacidad_max:
            raise HTTPException(status_code=400, detail="Capacidad insuficiente en el contenedor. Otro movimiento lo llenó recientemente.")
        container.ocupacion_actual += movimiento.cantidad
        container.fecha_ultimo_movimiento = datetime.utcnow()
        
    elif movimiento.tipo == "salida_produccion":
        if container.ocupacion_actual < movimiento.cantidad:
            raise HTTPException(status_code=400, detail="Stock insuficiente en este momento para originar la salida.")
        container.ocupacion_actual -= movimiento.cantidad
        container.fecha_ultimo_movimiento = datetime.utcnow()
        
    elif movimiento.tipo == "traslado_interno":
        # Por si alguno llegó como pendiente por un offline sync
        container_dst = (await db.execute(select(Container).where(Container.id == movimiento.id_container_destino))).scalars().first()
        if container.ocupacion_actual < movimiento.cantidad:
            raise HTTPException(status_code=400, detail="Stock insuficiente en origen.")
        if container_dst.ocupacion_actual + movimiento.cantidad > container_dst.capacidad_max:
             raise HTTPException(status_code=400, detail="Capacidad insuficiente en el destino.")
        
        container.ocupacion_actual -= movimiento.cantidad
        container_dst.ocupacion_actual += movimiento.cantidad
        container.fecha_ultimo_movimiento = datetime.utcnow()
        container_dst.fecha_ultimo_movimiento = datetime.utcnow()
        

    movimiento.estado = "aprobado"
    movimiento.id_usuario_aprobador = current_user.id
    movimiento.fecha_aprobacion = datetime.utcnow()

    # Auditoría rigurosa
    await log_action(db, current_user.id, "APROBAR_MOVIMIENTO", "Movimiento", str(movimiento.id), {"aprobador_id_rut_enc": current_user.id})

    await db.commit()
    await db.refresh(movimiento)

    # Disparar alertas instantáneas post-aprobación
    await evaluar_alertas(movimiento.id_container, db)
    if movimiento.id_container_destino:
        await evaluar_alertas(movimiento.id_container_destino, db)

    return movimiento

@router.patch("/{id}/rechazar", response_model=MovimientoRead)
async def rechazar_movimiento(
    id: str,
    payload: MovimientoRechazar,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role(["jefe_bodega", "super_admin"]))
) -> Any:
    movimiento = (await db.execute(select(Movimiento).where(Movimiento.id == id))).scalars().first()
    if not movimiento:
        raise HTTPException(status_code=404, detail="Movimiento no encontrado")

    if movimiento.estado != "pendiente":
        raise HTTPException(status_code=400, detail=f"El movimiento ya se encuentra {movimiento.estado}")

    movimiento.estado = "rechazado"
    movimiento.id_usuario_aprobador = current_user.id
    movimiento.fecha_aprobacion = datetime.utcnow()
    movimiento.motivo_rechazo = payload.motivo_rechazo

    await log_action(db, current_user.id, "RECHAZAR_MOVIMIENTO", "Movimiento", str(movimiento.id), {"motivo": payload.motivo_rechazo})
    
    await db.commit()
    await db.refresh(movimiento)
    return movimiento

@router.get("/pendientes")
async def read_movimientos_pendientes(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role(["jefe_bodega", "super_admin"]))
) -> Any:
    # Aislamiento Multi-Sede Estricto Crítico
    stmt = (
        select(Movimiento)
        .join(Container, Movimiento.id_container == Container.id)
        .join(Galpon, Container.id_galpon == Galpon.id)
        .where(Movimiento.estado == "pendiente")
    )
    
    if current_user.rol != "super_admin":
        if current_user.id_sede:
            stmt = stmt.where(Galpon.id_sede == current_user.id_sede)

    result = await db.execute(stmt)
    movimientos = result.scalars().all()
    # Mapeo a Model schema para omitir RUTS (pydantic model configuration)
    return [MovimientoRead.model_validate(m) for m in movimientos]

# Endpoint Offline Sync Placeholder
@router.post("/sync", status_code=status.HTTP_201_CREATED)
async def sync_movimientos(
    movimientos_offline: list[dict],
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user)
) -> Any:
    # 1. Estrategia Last-Write-Wins con mitigación de capacidad.
    # Esta es una implementación básica del conflicto
    resultados = []
    for mov in movimientos_offline:
        container = (await db.execute(select(Container).where(Container.id == mov["id_container"]))).scalars().first()
        if not container:
            resultados.append({"uuid_local": mov["uuid_local"], "accion": "rechazar", "motivo": "Container eliminado"})
            continue
            
        if mov["tipo"] == "entrada_proveedor":
            if container.ocupacion_actual + float(mov["cantidad"]) > container.capacidad_max:
                resultados.append({"uuid_local": mov["uuid_local"], "accion": "rechazar", "motivo": f"Sin capacidad. Físicamente quedan {container.capacidad_max - container.ocupacion_actual} unidades."})
                continue
        # Implementar la creación segura y devolver OK
        resultados.append({"uuid_local": mov["uuid_local"], "accion": "aplicar", "motivo": "OK"})
        
    return {"resultados": resultados}

