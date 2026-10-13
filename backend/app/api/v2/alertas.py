import math
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies_v2 import TenantContext, get_current_tenant
from app.core.audit import log_action
from app.core.site_access import scope_alert_query
from app.database import get_db
from app.models.v2.alerta import AlertaV2, ReglaAlertaV2
from app.schemas.v2.alerta import (
    AlertaRead,
    AlertaResolver,
    AlertaRevisar,
    EvaluarAlertasResultado,
    ReglaAlertaCreate,
    ReglaAlertaRead,
    ReglaAlertaUpdate,
)
from app.schemas.v2.common import PaginatedResponse
from app.services.v2.alerta_service import AlertaServiceV2

router = APIRouter(prefix="/alertas", tags=["V2 - Alertas y Reglas"])


# ─── Reglas de Alerta Configurables ──────────────────────────────────────────

@router.get("/reglas", response_model=List[ReglaAlertaRead])
async def listar_reglas_alerta(
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Lista las reglas de alertas configuradas para la organización."""
    await AlertaServiceV2.inicializar_plantillas(db, tenant.id_organizacion)
    stmt = select(ReglaAlertaV2).where(
        ReglaAlertaV2.id_organizacion == tenant.id_organizacion
    ).order_by(ReglaAlertaV2.codigo.asc())
    res = await db.execute(stmt)
    return res.scalars().all()


@router.post("/reglas", response_model=ReglaAlertaRead, status_code=status.HTTP_201_CREATED)
async def crear_regla_alerta(
    data: ReglaAlertaCreate,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Crea una regla de alerta personalizada para la organización."""
    if not tenant.tiene_permiso("rbac:manage") and tenant.rol_codigo not in ("super_admin", "admin_sede"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente para configurar reglas de alerta")

    stmt_dup = select(ReglaAlertaV2).where(
        ReglaAlertaV2.id_organizacion == tenant.id_organizacion,
        ReglaAlertaV2.codigo == data.codigo,
    )
    dup = (await db.execute(stmt_dup)).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya existe una regla con este código en la organización")

    regla = ReglaAlertaV2(
        id_organizacion=tenant.id_organizacion,
        codigo=data.codigo,
        nombre=data.nombre,
        tipo=data.tipo,
        configuracion=data.configuracion,
        severidad=data.severidad,
        habilitada=data.habilitada,
    )
    db.add(regla)
    await db.flush()
    await log_action(db, tenant.usuario.id, "CREAR_REGLA_ALERTA_V2", "v2_regla_alerta",
                     regla.id, {"id_organizacion": tenant.id_organizacion, "codigo": regla.codigo})
    await db.commit()
    await db.refresh(regla)
    return regla


@router.patch("/reglas/{id}", response_model=ReglaAlertaRead)
async def actualizar_regla_alerta(
    id: str,
    data: ReglaAlertaUpdate,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Modifica dinámicamente los umbrales o estado de activación de una regla."""
    if not tenant.tiene_permiso("rbac:manage") and tenant.rol_codigo not in ("super_admin", "admin_sede"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente para configurar reglas de alerta")

    stmt = select(ReglaAlertaV2).where(
        ReglaAlertaV2.id == id,
        ReglaAlertaV2.id_organizacion == tenant.id_organizacion,
    )
    regla = (await db.execute(stmt)).scalar_one_or_none()
    if not regla:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Regla de alerta no encontrada")

    if data.nombre is not None:
        regla.nombre = data.nombre
    if data.configuracion is not None:
        regla.configuracion = data.configuracion
    if data.severidad is not None:
        regla.severidad = data.severidad
    if data.habilitada is not None:
        regla.habilitada = data.habilitada

    await log_action(db, tenant.usuario.id, "ACTUALIZAR_REGLA_ALERTA_V2", "v2_regla_alerta",
                     regla.id, {"id_organizacion": tenant.id_organizacion,
                                "campos": sorted(data.model_fields_set)})

    await db.commit()
    await db.refresh(regla)
    return regla


# ─── Alertas Generadas ────────────────────────────────────────────────────────

@router.get("/activas", response_model=List[AlertaRead])
async def listar_alertas_activas(
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Retorna las alertas actualmente activas para la organización."""
    stmt = (
        select(AlertaV2)
        .where(
            AlertaV2.id_organizacion == tenant.id_organizacion,
            AlertaV2.estado == "activa",
        )
        .order_by(AlertaV2.fecha_generacion.desc())
    )
    stmt = scope_alert_query(stmt, tenant, AlertaV2)
    res = await db.execute(stmt)
    return res.scalars().all()


@router.get("", response_model=PaginatedResponse[AlertaRead])
async def listar_alertas(
    estado: Optional[str] = Query(None, description="Filtrar por estado: activa, revisada, resuelta"),
    severidad: Optional[str] = Query(None, description="Filtrar por severidad: critica, aviso, informativa"),
    tipo: Optional[str] = Query(None, description="Filtrar por tipo"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Lista historial de alertas paginado con filtros para la organización."""
    base_filter = [AlertaV2.id_organizacion == tenant.id_organizacion]
    if estado:
        base_filter.append(AlertaV2.estado == estado)
    if severidad:
        base_filter.append(AlertaV2.severidad == severidad)
    if tipo:
        base_filter.append(AlertaV2.tipo == tipo)

    stmt_total = scope_alert_query(select(func.count(AlertaV2.id)).where(*base_filter), tenant, AlertaV2)
    total = (await db.execute(stmt_total)).scalar_one()

    offset = (page - 1) * page_size
    stmt_items = (
        select(AlertaV2)
        .where(*base_filter)
        .order_by(AlertaV2.fecha_generacion.desc())
        .offset(offset)
        .limit(page_size)
    )
    stmt_items = scope_alert_query(stmt_items, tenant, AlertaV2)
    items = (await db.execute(stmt_items)).scalars().all()

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total > 0 else 0,
    )


@router.post("/evaluar", response_model=EvaluarAlertasResultado)
async def disparar_evaluacion_alertas(
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Ejecuta la evaluación de todas las reglas habilitadas para la organización."""
    if not tenant.tiene_permiso("rbac:manage"):
        raise HTTPException(status_code=403, detail="Permiso insuficiente")
    nuevas = await AlertaServiceV2.evaluar_alertas(db, tenant.id_organizacion)
    await db.commit()
    await AlertaServiceV2.notificar_alertas(db, tenant.id_organizacion, nuevas)

    stmt_count_reglas = select(func.count(ReglaAlertaV2.id)).where(
        ReglaAlertaV2.id_organizacion == tenant.id_organizacion,
        ReglaAlertaV2.habilitada == True,
    )
    reglas_evaluadas = (await db.execute(stmt_count_reglas)).scalar_one()

    return EvaluarAlertasResultado(
        reglas_evaluadas=reglas_evaluadas,
        nuevas_alertas=len(nuevas),
        alertas_creadas=[AlertaRead.model_validate(a) for a in nuevas],
    )


@router.patch("/{id}/revisar", response_model=AlertaRead)
async def marcar_alerta_revisada(
    id: str,
    payload: AlertaRevisar = AlertaRevisar(),
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Marca una alerta como revisada por el supervisor."""
    return await AlertaServiceV2.revisar_alerta(db, tenant, id, payload.observaciones)


@router.patch("/{id}/resolver", response_model=AlertaRead)
async def marcar_alerta_resuelta(
    id: str,
    payload: AlertaResolver = AlertaResolver(),
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Marca una alerta como resuelta."""
    return await AlertaServiceV2.resolver_alerta(db, tenant, id, payload.observaciones)
