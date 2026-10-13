import json
import math
from typing import List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies_v2 import TenantContext, get_current_tenant
from app.core.modules.registry import require_module_enabled
from app.database import get_db
from app.modules.importacion.models import ImportacionJob, Inconsistencia, MappingProfile
from app.modules.importacion.schemas import (
    ConciliacionResultado,
    ImportacionJobRead,
    InconsistenciaRead,
    MappingProfileCreate,
    MappingProfileRead,
    MappingProfileUpdate,
)
from app.modules.importacion.services.conciliador import ConciliadorService
from app.modules.importacion.services.mapping import MappingService
from app.modules.importacion.services.parser_csv import parsear_csv
from app.modules.importacion.services.parser_excel import parsear_excel
from app.schemas.v2.common import PaginatedResponse

router = APIRouter(prefix="/importacion", tags=["V2 - Importación y Conciliación ERP/WMS"],
                   dependencies=[Depends(require_module_enabled("importacion"))])
MAX_IMPORT_BYTES = 10 * 1024 * 1024


# ─── Perfiles de Mapeo Configurables ─────────────────────────────────────────

@router.get("/mapeos", response_model=List[MappingProfileRead])
async def listar_perfiles_mapeo(
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Lista los perfiles de mapeo de columnas guardados para la organización."""
    stmt = (
        select(MappingProfile)
        .where(
            MappingProfile.id_organizacion == tenant.id_organizacion,
            MappingProfile.activo == True,
        )
        .order_by(MappingProfile.nombre.asc())
    )
    res = await db.execute(stmt)
    return res.scalars().all()


@router.post("/mapeos", response_model=MappingProfileRead, status_code=status.HTTP_201_CREATED)
async def crear_perfil_mapeo(
    data: MappingProfileCreate,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Crea y guarda un perfil de mapeo reutilizable para importaciones de ERP/WMS."""
    stmt_dup = select(MappingProfile).where(
        MappingProfile.id_organizacion == tenant.id_organizacion,
        MappingProfile.nombre == data.nombre,
    )
    dup = (await db.execute(stmt_dup)).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ya existe un perfil con este nombre")

    perfil = MappingProfile(
        id_organizacion=tenant.id_organizacion,
        nombre=data.nombre,
        descripcion=data.descripcion,
        mapeo=data.mapeo,
        activo=True,
    )
    db.add(perfil)
    await db.commit()
    await db.refresh(perfil)
    return perfil


@router.patch("/mapeos/{id}", response_model=MappingProfileRead)
async def actualizar_perfil_mapeo(
    id: str,
    data: MappingProfileUpdate,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Actualiza o desactiva un perfil de mapeo."""
    stmt = select(MappingProfile).where(
        MappingProfile.id == id,
        MappingProfile.id_organizacion == tenant.id_organizacion,
    )
    perfil = (await db.execute(stmt)).scalar_one_or_none()
    if not perfil:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Perfil de mapeo no encontrado")

    if data.nombre is not None:
        perfil.nombre = data.nombre
    if data.descripcion is not None:
        perfil.descripcion = data.descripcion
    if data.mapeo is not None:
        perfil.mapeo = data.mapeo
    if data.activo is not None:
        perfil.activo = data.activo

    await db.commit()
    await db.refresh(perfil)
    return perfil


# ─── Proceso de Importación y Conciliación ───────────────────────────────────

@router.post("/conciliar", response_model=ConciliacionResultado)
async def conciliar_archivo_externo(
    file: UploadFile = File(..., description="Archivo CSV o Excel (.xlsx) emitido por el ERP/WMS"),
    id_mapping_profile: Optional[str] = Form(None, description="ID del perfil de mapeo guardado"),
    mapeo_json: Optional[str] = Form(None, description="Mapeo inline JSON alternativo"),
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Sube un archivo externo (CSV o Excel), normaliza las columnas según el mapeo y concilia
    las existencias contra SalmoTrack v2, detectando sobrecapacidad, mezclas prohibidas e inexistencias.
    """
    filename = file.filename or "archivo_externo"
    extension = filename.split(".")[-1].lower() if "." in filename else ""

    if extension not in ("csv", "xlsx"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Formato no soportado. Sólo se admiten archivos .csv y .xlsx",
        )

    # 1. Resolver el mapeo a utilizar
    mapeo_dict = {}
    if id_mapping_profile:
        stmt_m = select(MappingProfile).where(
            MappingProfile.id == id_mapping_profile,
            MappingProfile.id_organizacion == tenant.id_organizacion,
        )
        perfil = (await db.execute(stmt_m)).scalar_one_or_none()
        if not perfil:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Perfil de mapeo no encontrado")
        mapeo_dict = perfil.mapeo
    elif mapeo_json:
        try:
            mapeo_dict = json.loads(mapeo_json)
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El parámetro mapeo_json no es un JSON válido")
    else:
        # Mapeo por defecto según nombres estándar
        mapeo_dict = {
            "codigo_ubicacion": "POSICION",
            "codigo_item": "SKU",
            "numero_lote": "LOTE",
            "cantidad": "CANTIDAD",
        }

    # 2. Parsear el archivo según extensión
    contenido = await file.read(MAX_IMPORT_BYTES + 1)
    if len(contenido) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail="El archivo supera el límite de 10 MB")
    if extension == "csv":
        filas_crudas = parsear_csv(contenido)
        tipo_fuente = "csv"
    else:
        filas_crudas = parsear_excel(contenido)
        tipo_fuente = "excel"

    if not filas_crudas:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo subido está vacío o no contiene filas")

    # 3. Normalizar filas
    filas_normalizadas = MappingService.normalizar_filas(filas_crudas, mapeo_dict)

    # 4. Conciliar
    job = await ConciliadorService.conciliar(
        db=db,
        tenant=tenant,
        nombre_archivo=filename,
        tipo_fuente=tipo_fuente,
        filas_normalizadas=filas_normalizadas,
        id_mapping_profile=id_mapping_profile,
    )

    stmt_inc = select(Inconsistencia).where(Inconsistencia.id_importacion_job == job.id).order_by(Inconsistencia.fila_origen.asc())
    inconsistencias = (await db.execute(stmt_inc)).scalars().all()

    return ConciliacionResultado(
        job=ImportacionJobRead.model_validate(job),
        inconsistencias=[InconsistenciaRead.model_validate(inc) for inc in inconsistencias],
    )


# ─── Consultas de Jobs e Inconsistencias ──────────────────────────────────────

@router.get("/jobs", response_model=PaginatedResponse[ImportacionJobRead])
async def listar_jobs_importacion(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Lista historial paginado de ejecuciones de importación y conciliación."""
    stmt_total = select(func.count(ImportacionJob.id)).where(ImportacionJob.id_organizacion == tenant.id_organizacion)
    total = (await db.execute(stmt_total)).scalar_one()

    offset = (page - 1) * page_size
    stmt_items = (
        select(ImportacionJob)
        .where(ImportacionJob.id_organizacion == tenant.id_organizacion)
        .order_by(ImportacionJob.fecha_inicio.desc())
        .offset(offset)
        .limit(page_size)
    )
    items = (await db.execute(stmt_items)).scalars().all()

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total > 0 else 0,
    )


@router.get("/jobs/{id}/inconsistencias", response_model=List[InconsistenciaRead])
async def consultar_inconsistencias_job(
    id: str,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Consulta la lista de inconsistencias detectadas en una ejecución específica."""
    stmt_job = select(ImportacionJob).where(
        ImportacionJob.id == id,
        ImportacionJob.id_organizacion == tenant.id_organizacion,
    )
    job = (await db.execute(stmt_job)).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job de importación no encontrado")

    stmt_inc = (
        select(Inconsistencia)
        .where(
            Inconsistencia.id_importacion_job == job.id,
            Inconsistencia.id_organizacion == tenant.id_organizacion,
        )
        .order_by(Inconsistencia.fila_origen.asc())
    )
    res = await db.execute(stmt_inc)
    return res.scalars().all()
