import math
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies_v2 import TenantContext, get_current_tenant
from app.database import get_db
from app.models.v2.movimiento import MovimientoV2
from app.models.v2.saldo_stock import SaldoStock
from app.models.v2.solicitud_movimiento import SolicitudMovimiento
from app.models.v2.tipo_movimiento import TipoMovimiento
from app.schemas.v2.common import PaginatedResponse
from app.schemas.v2.movimiento import (
    MovimientoV2Read,
    SaldoStockRead,
    SolicitudMovimientoCreate,
    SolicitudMovimientoRead,
    SolicitudRechazar,
    TipoMovimientoCreate,
    TipoMovimientoRead,
)
from app.schemas.v2.sync import SyncBatchRequest, SyncBatchResponse
from app.services.v2.movimiento_service import MovimientoService
from app.services.v2.sync_service import OfflineSyncService

router = APIRouter(prefix="/movimientos", tags=["V2 - Movimientos"])


# ─── Tipos de Movimiento Configurables ───────────────────────────────────────

@router.get("/tipos", response_model=List[TipoMovimientoRead])
async def listar_tipos_movimiento(
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Lista los tipos de movimiento configurados para la organización."""
    stmt = select(TipoMovimiento).where(
        TipoMovimiento.id_organizacion == tenant.id_organizacion,
        TipoMovimiento.activo == True,
    ).order_by(TipoMovimiento.codigo.asc())
    res = await db.execute(stmt)
    return res.scalars().all()


@router.post("/tipos", response_model=TipoMovimientoRead, status_code=status.HTTP_201_CREATED)
async def crear_tipo_movimiento(
    data: TipoMovimientoCreate,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Registra un nuevo tipo de movimiento configurable."""
    if not tenant.tiene_permiso("rbac:manage") and tenant.rol_codigo not in ("super_admin", "admin_sede"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente para configurar tipos de movimiento")

    stmt_dup = select(TipoMovimiento).where(
        TipoMovimiento.id_organizacion == tenant.id_organizacion,
        TipoMovimiento.codigo == data.codigo,
    )
    dup = (await db.execute(stmt_dup)).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Tipo de movimiento '{data.codigo}' ya existe")

    tipo = TipoMovimiento(
        id_organizacion=tenant.id_organizacion,
        codigo=data.codigo,
        nombre=data.nombre,
        efecto_stock=data.efecto_stock,
        requiere_origen=data.requiere_origen,
        requiere_destino=data.requiere_destino,
        requiere_aprobacion=data.requiere_aprobacion,
        activo=True,
    )
    db.add(tipo)
    await db.commit()
    await db.refresh(tipo)
    return tipo


# ─── Solicitudes de Movimiento ────────────────────────────────────────────────

@router.post("/solicitudes", response_model=SolicitudMovimientoRead, status_code=status.HTTP_201_CREATED)
async def crear_solicitud_movimiento(
    data: SolicitudMovimientoCreate,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Crea una solicitud de movimiento; si el tipo no requiere aprobación, se confirma de inmediato."""
    if not tenant.tiene_permiso("movimiento:create"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente para registrar movimientos")

    solicitud = await MovimientoService.crear_solicitud(
        db=db,
        tenant=tenant,
        id_tipo_movimiento=data.id_tipo_movimiento,
        id_item=data.id_item,
        cantidad=data.cantidad,
        unidad_medida=data.unidad_medida,
        id_lote=data.id_lote,
        id_ubicacion_origen=data.id_ubicacion_origen,
        id_ubicacion_destino=data.id_ubicacion_destino,
        observaciones=data.observaciones,
        uuid_local=data.uuid_local,
        atributos=data.atributos,
    )
    return solicitud


@router.get("/solicitudes", response_model=PaginatedResponse[SolicitudMovimientoRead])
async def listar_solicitudes(
    estado: Optional[str] = Query(None, description="Filtrar por estado (pendiente, aprobada, rechazada)"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Lista solicitudes de movimiento de la organización con paginación."""
    stmt = select(SolicitudMovimiento).where(SolicitudMovimiento.id_organizacion == tenant.id_organizacion)
    if estado:
        stmt = stmt.where(SolicitudMovimiento.estado == estado)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = stmt.order_by(SolicitudMovimiento.fecha_creacion.desc()).offset((page - 1) * size).limit(size)
    res = await db.execute(stmt)
    items = res.scalars().all()

    pages = math.ceil(total / size) if total > 0 else 1
    return PaginatedResponse(items=items, total=total, page=page, size=size, pages=pages)


@router.patch("/solicitudes/{id_solicitud}/aprobar", response_model=MovimientoV2Read)
async def aprobar_solicitud(
    id_solicitud: str,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Aprueba una solicitud pendiente: actualiza existencias atómicamente y emite el movimiento inmutable."""
    if not tenant.tiene_permiso("movimiento:approve"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente para aprobar movimientos")

    movimiento = await MovimientoService.aprobar_solicitud(db, tenant, id_solicitud)
    return movimiento


@router.patch("/solicitudes/{id_solicitud}/rechazar", response_model=SolicitudMovimientoRead)
async def rechazar_solicitud(
    id_solicitud: str,
    payload: SolicitudRechazar,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Rechaza una solicitud de movimiento registrando el motivo y manteniendo la auditoría."""
    if not tenant.tiene_permiso("movimiento:reject"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente para rechazar movimientos")

    solicitud = await MovimientoService.rechazar_solicitud(db, tenant, id_solicitud, payload.motivo)
    return solicitud


# ─── Movimientos Inmutables y Trazabilidad ───────────────────────────────────

@router.get("/", response_model=PaginatedResponse[MovimientoV2Read])
async def listar_movimientos(
    efecto_stock: Optional[str] = Query(None, description="Filtrar por efecto (entrada, salida, traslado)"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Consulta el libro inmutable de movimientos confirmados de la organización."""
    stmt = select(MovimientoV2).where(MovimientoV2.id_organizacion == tenant.id_organizacion)
    if efecto_stock:
        stmt = stmt.where(MovimientoV2.efecto_stock == efecto_stock)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = stmt.order_by(MovimientoV2.fecha_hora.desc()).offset((page - 1) * size).limit(size)
    res = await db.execute(stmt)
    items = res.scalars().all()

    pages = math.ceil(total / size) if total > 0 else 1
    return PaginatedResponse(items=items, total=total, page=page, size=size, pages=pages)


@router.get("/trazabilidad", response_model=List[MovimientoV2Read])
async def consultar_trazabilidad(
    id_lote: Optional[str] = Query(None, description="Consultar historial por lote"),
    id_item: Optional[str] = Query(None, description="Consultar historial por ítem"),
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Retorna la cadena inmutable de custodia para un lote o ítem específico."""
    if not id_lote and not id_item:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Debe especificar id_lote o id_item para trazabilidad")

    stmt = select(MovimientoV2).where(MovimientoV2.id_organizacion == tenant.id_organizacion)
    if id_lote:
        stmt = stmt.where(MovimientoV2.id_lote == id_lote)
    if id_item:
        stmt = stmt.where(MovimientoV2.id_item == id_item)

    stmt = stmt.order_by(MovimientoV2.fecha_hora.asc())
    res = await db.execute(stmt)
    return res.scalars().all()


@router.get("/saldos", response_model=List[SaldoStockRead])
async def consultar_saldos(
    id_ubicacion: Optional[str] = Query(None, description="Filtrar por ubicación"),
    id_item: Optional[str] = Query(None, description="Filtrar por ítem"),
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Consulta los saldos de stock consolidados por ubicación, ítem o lote."""
    stmt = select(SaldoStock).where(SaldoStock.id_organizacion == tenant.id_organizacion)
    if id_ubicacion:
        stmt = stmt.where(SaldoStock.id_ubicacion == id_ubicacion)
    if id_item:
        stmt = stmt.where(SaldoStock.id_item == id_item)

    stmt = stmt.order_by(SaldoStock.fecha_actualizacion.desc())
    res = await db.execute(stmt)
    return res.scalars().all()


# ─── Sincronización Offline (Fase 1C) ────────────────────────────────────────

@router.post("/sync", response_model=SyncBatchResponse)
async def sincronizar_movimientos_offline(
    batch: SyncBatchRequest,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Sincroniza un lote de movimientos generados sin conexión en cliente PWA / Dexie.js.
    Aplica idempotencia por uuid_local y garantiza aislamiento transaccional por movimiento.
    """
    if not tenant.tiene_permiso("movimiento:create"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente para sincronizar movimientos")

    return await OfflineSyncService.procesar_lote_sync(db, tenant, batch)
