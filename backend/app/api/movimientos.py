from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
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
from app.services.fefo import sugerir_container_fefo
from app.services.picking import obtener_containers_para_picking, optimizar_ruta
from app.services.sync import procesar_sync
from app.websockets import manager

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
        container.ultimo_movimiento = datetime.utcnow()
        container_dst.ocupacion_actual += mov_in.cantidad
        container_dst.ultimo_movimiento = datetime.utcnow()
        # Se evalúan alertas más abajo si es necesario
    else:
        # correcciones u otros
        movimiento.estado = "pendiente"

    db.add(movimiento)
    await db.commit()
    await db.refresh(movimiento)
    
    await log_action(db, current_user.id, "REGISTRAR_MOVIMIENTO", "Movimiento", str(movimiento.id), {"tipo": mov_in.tipo, "estado": movimiento.estado})
    
    if mov_in.tipo == "traslado_interno":
        await evaluar_alertas(container.id, db, manager=manager)
        await evaluar_alertas(container_dst.id, db, manager=manager)

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
        container.ultimo_movimiento = datetime.utcnow()

    elif movimiento.tipo == "salida_produccion":
        if container.ocupacion_actual < movimiento.cantidad:
            raise HTTPException(status_code=400, detail="Stock insuficiente en este momento para originar la salida.")
        container.ocupacion_actual -= movimiento.cantidad
        container.ultimo_movimiento = datetime.utcnow()
        
    elif movimiento.tipo == "traslado_interno":
        # Por si alguno llegó como pendiente por un offline sync
        container_dst = (await db.execute(select(Container).where(Container.id == movimiento.id_container_destino))).scalars().first()
        if container.ocupacion_actual < movimiento.cantidad:
            raise HTTPException(status_code=400, detail="Stock insuficiente en origen.")
        if container_dst.ocupacion_actual + movimiento.cantidad > container_dst.capacidad_max:
             raise HTTPException(status_code=400, detail="Capacidad insuficiente en el destino.")
        
        container.ocupacion_actual -= movimiento.cantidad
        container_dst.ocupacion_actual += movimiento.cantidad
        container.ultimo_movimiento = datetime.utcnow()
        container_dst.ultimo_movimiento = datetime.utcnow()
        

    movimiento.estado = "aprobado"
    movimiento.id_usuario_aprobador = current_user.id
    movimiento.fecha_aprobacion = datetime.utcnow()

    # Auditoría rigurosa
    await log_action(db, current_user.id, "APROBAR_MOVIMIENTO", "Movimiento", str(movimiento.id), {"aprobador_id_rut_enc": current_user.id})

    await db.commit()
    await db.refresh(movimiento)

    # Disparar alertas instantáneas post-aprobación
    await evaluar_alertas(movimiento.id_container, db, manager=manager)
    if movimiento.id_container_destino:
        await evaluar_alertas(movimiento.id_container_destino, db, manager=manager)

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

@router.get("/fefo")
async def fefo(
    id_producto: str,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> Any:
    """AXI-11 — Sugiere containers ordenados por fecha_vencimiento ASC (FEFO)."""
    id_sede = current_user.id_sede
    if not id_sede:
        raise HTTPException(status_code=400, detail="El usuario no tiene sede asignada.")
    resultado = await sugerir_container_fefo(db, id_producto, id_sede)
    return {"containers_fefo": resultado, "total": len(resultado)}


@router.get("/trazabilidad")
async def trazabilidad(
    numero_lote: str,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role(["jefe_bodega", "admin_sede", "super_admin", "gerencia"])),
) -> Any:
    """AXI-12 — Historial completo de un lote (usa indice GIN para < 2s)."""
    stmt = (
        select(
            Movimiento.id,
            Movimiento.tipo,
            Movimiento.estado,
            Movimiento.cantidad,
            Movimiento.numero_lote,
            Movimiento.fecha_hora,
            Movimiento.fecha_vencimiento,
            Movimiento.nombre_proveedor,
            Movimiento.num_guia_despacho,
            Movimiento.registro_sanitario,
            Movimiento.id_usuario,
            Movimiento.id_container,
        )
        .where(Movimiento.numero_lote == numero_lote)
        .order_by(Movimiento.fecha_hora.asc())
    )
    # Aislamiento multi-sede para roles no globales
    if current_user.rol not in ("super_admin", "gerencia"):
        stmt = (
            stmt
            .join(Container, Movimiento.id_container == Container.id)
            .join(Galpon, Container.id_galpon == Galpon.id)
            .where(Galpon.id_sede == current_user.id_sede)
        )
    rows = (await db.execute(stmt)).mappings().all()
    return {"numero_lote": numero_lote, "movimientos": [dict(r) for r in rows], "total": len(rows)}


@router.get("/ruta-picking")
async def ruta_picking(
    containers: str = Query(..., description="IDs separados por coma"),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> Any:
    """AXI-21 — Ruta optima de picking (Nearest Neighbor, Manhattan)."""
    ids = [c.strip() for c in containers.split(",") if c.strip()]
    if not ids:
        raise HTTPException(status_code=400, detail="Se requiere al menos un container.")
    if len(ids) > 50:
        raise HTTPException(status_code=400, detail="Maximo 50 containers por pedido.")
    if not current_user.id_sede:
        raise HTTPException(status_code=400, detail="El usuario no tiene sede asignada.")

    datos = await obtener_containers_para_picking(db, ids, current_user.id_sede)
    if not datos:
        raise HTTPException(status_code=404, detail="Ningun container encontrado en tu sede.")

    return optimizar_ruta(datos)


@router.post("/sync", status_code=status.HTTP_201_CREATED)
async def sync_movimientos(
    movimientos_offline: list[dict],
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
) -> Any:
    """AXI-13 — Sincronizacion offline real. Last-Write-Wins + validacion capacidad."""
    if not movimientos_offline:
        return {"resultados": []}
    resultados = await procesar_sync(movimientos_offline, str(current_user.id), db)
    return {"resultados": resultados}

