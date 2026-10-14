import json
import math
from typing import List, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies_v2 import TenantContext, get_current_tenant, require_permission
from app.core.modules.registry import require_module_enabled
from app.core.site_access import allowed_location_ids
from app.database import get_db
from app.modules.importacion.models import ImportacionJob, Inconsistencia, MappingProfile
from app.modules.importacion.schemas import (
    ConciliacionResultado,
    ImportacionJobRead,
    InconsistenciaRead,
    ImportacionAPIRequest,
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
                   dependencies=[Depends(require_module_enabled("importacion")),
                                 Depends(require_permission("reporte:export"))])
MAX_IMPORT_BYTES = 10 * 1024 * 1024
MAPEO_DEFAULT = {
    "codigo_sitio": "SITIO", "codigo_zona": "ZONA",
    "codigo_ubicacion": "POSICION", "codigo_item": "SKU",
    "numero_lote": "LOTE", "cantidad": "CANTIDAD",
}


async def _resolver_mapeo(db: AsyncSession, tenant: TenantContext,
                          id_perfil: Optional[str], inline: Optional[dict]) -> dict:
    if id_perfil and inline is not None:
        raise HTTPException(status_code=400, detail="Indique perfil o mapeo inline, no ambos")
    if id_perfil:
        perfil = (await db.execute(select(MappingProfile).where(
            MappingProfile.id == id_perfil,
            MappingProfile.id_organizacion == tenant.id_organizacion,
            MappingProfile.activo.is_(True),
        ))).scalar_one_or_none()
        if not perfil:
            raise HTTPException(status_code=404, detail="Perfil de mapeo no encontrado")
        return perfil.mapeo
    return inline if inline is not None else MAPEO_DEFAULT


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
    inline = None
    if mapeo_json:
        try:
            inline = json.loads(mapeo_json)
            if not isinstance(inline, dict):
                raise ValueError("Se esperaba un objeto")
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El parámetro mapeo_json no es un JSON válido")
    mapeo_dict = await _resolver_mapeo(db, tenant, id_mapping_profile, inline)

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


@router.post("/conciliar-api", response_model=ConciliacionResultado)
async def conciliar_datos_api(
    data: ImportacionAPIRequest,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Concilia filas JSON recibidas de un ERP/WMS usando el mismo motor que CSV/Excel."""
    if len(json.dumps(data.filas, ensure_ascii=False).encode("utf-8")) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="Los datos superan el límite de 10 MB")
    mapeo = data.mapeo
    if not data.id_mapping_profile and mapeo is None and "codigo_ubicacion" in data.filas[0]:
        mapeo = {campo: campo for campo in MAPEO_DEFAULT}
    mapeo = await _resolver_mapeo(db, tenant, data.id_mapping_profile, mapeo)
    normalizadas = MappingService.normalizar_filas(data.filas, mapeo)
    job = await ConciliadorService.conciliar(
        db=db, tenant=tenant, nombre_archivo=f"api:{data.fuente}", tipo_fuente="api",
        filas_normalizadas=normalizadas, id_mapping_profile=data.id_mapping_profile,
    )
    inconsistencias = (await db.execute(select(Inconsistencia).where(
        Inconsistencia.id_importacion_job == job.id,
        Inconsistencia.id_organizacion == tenant.id_organizacion,
    ).order_by(Inconsistencia.fila_origen.asc()))).scalars().all()
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
    base = [ImportacionJob.id_organizacion == tenant.id_organizacion]
    if tenant.sitios_permitidos is not None:
        base.append(ImportacionJob.id_usuario == tenant.usuario.id)
    stmt_total = select(func.count(ImportacionJob.id)).where(*base)
    total = (await db.execute(stmt_total)).scalar_one()

    offset = (page - 1) * page_size
    stmt_items = (
        select(ImportacionJob)
        .where(*base)
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
    if tenant.sitios_permitidos is not None:
        stmt_job = stmt_job.where(ImportacionJob.id_usuario == tenant.usuario.id)
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
    if tenant.sitios_permitidos is not None:
        stmt_inc = stmt_inc.where(Inconsistencia.id_ubicacion.in_(allowed_location_ids(tenant)))
    res = await db.execute(stmt_inc)
    return res.scalars().all()
