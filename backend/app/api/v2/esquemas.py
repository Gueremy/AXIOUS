from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
import jsonschema
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies_v2 import TenantContext, get_current_tenant
from app.database import get_db
from app.models.v2.esquema_atributos import EsquemaAtributos
from app.schemas.v2.esquema_atributos import EsquemaAtributosCreate, EsquemaAtributosRead

router = APIRouter(prefix="/esquemas", tags=["V2 - Esquemas de Atributos"])


@router.get("/", response_model=List[EsquemaAtributosRead])
async def listar_esquemas(
    entidad: Optional[str] = Query(None, description="Filtrar por entidad (sitio, zona, ubicacion, item, lote)"),
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Lista definiciones de esquemas de atributos dinámicos de la organización."""
    if not tenant.tiene_permiso("esquema:read"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente")

    stmt = select(EsquemaAtributos).where(
        EsquemaAtributos.id_organizacion == tenant.id_organizacion,
        EsquemaAtributos.activo == True,
    )
    if entidad:
        stmt = stmt.where(EsquemaAtributos.entidad == entidad)

    stmt = stmt.order_by(EsquemaAtributos.entidad.asc(), EsquemaAtributos.version.desc())
    res = await db.execute(stmt)
    return res.scalars().all()


@router.post("/", response_model=EsquemaAtributosRead, status_code=status.HTTP_201_CREATED)
async def crear_esquema(
    data: EsquemaAtributosCreate,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Registra una nueva versión de esquema JSON Schema para validación de atributos dinámicos."""
    if not tenant.tiene_permiso("esquema:write"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente")

    # Validar que el esquema sea un JSON Schema válido sintácticamente
    try:
        jsonschema.Draft7Validator.check_schema(data.definicion_schema)
    except jsonschema.exceptions.SchemaError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Definición JSON Schema inválida: {e.message}")

    # Determinar siguiente versión si ya existe
    stmt_ver = select(func.max(EsquemaAtributos.version)).where(
        EsquemaAtributos.id_organizacion == tenant.id_organizacion,
        EsquemaAtributos.entidad == data.entidad,
        EsquemaAtributos.nombre == data.nombre,
    )
    max_ver = (await db.execute(stmt_ver)).scalar() or 0
    next_ver = max_ver + 1

    esquema = EsquemaAtributos(
        id_organizacion=tenant.id_organizacion,
        entidad=data.entidad,
        nombre=data.nombre,
        version=next_ver,
        schema_json=data.definicion_schema,
        activo=True,
    )
    db.add(esquema)
    await db.commit()
    await db.refresh(esquema)
    return esquema
