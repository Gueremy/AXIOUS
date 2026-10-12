"""
app/api/v2/layout.py
Backend para el editor visual de layout 2D/3D (Fase 3).
Permite persistir coordenadas, dimensiones espaciales y generar ubicaciones masivas.
"""
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies_v2 import TenantContext, get_current_tenant
from app.database import get_db
from app.models.log_auditoria import LogAuditoria
from app.models.v2.sitio import Sitio
from app.models.v2.ubicacion import Ubicacion
from app.models.v2.zona import Zona
from app.schemas.v2.layout import (
    LayoutSitioTree,
    LayoutUbicacionNode,
    LayoutUpdate,
    LayoutZonaNode,
    UbicacionBatchCreate,
)

router = APIRouter(prefix="/layout", tags=["V2 - Editor de Layout 2D/3D"])


@router.get("/sitios/{id_sitio}", response_model=LayoutSitioTree)
async def obtener_arbol_layout_sitio(
    id_sitio: str,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Retorna el árbol jerárquico completo de un sitio (zonas, subzonas y ubicaciones)
    con coordenadas y dimensiones 2D/3D para el renderizador visual del frontend.
    """
    stmt_s = select(Sitio).where(
        Sitio.id == id_sitio,
        Sitio.id_organizacion == tenant.id_organizacion,
        Sitio.activo == True,
    )
    sitio = (await db.execute(stmt_s)).scalar_one_or_none()
    if not sitio:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sitio no encontrado")

    # Cargar todas las zonas del sitio
    stmt_z = select(Zona).where(
        Zona.id_sitio == sitio.id,
        Zona.id_organizacion == tenant.id_organizacion,
        Zona.activo == True,
    ).order_by(Zona.codigo.asc())
    zonas_all = (await db.execute(stmt_z)).scalars().all()

    # Cargar todas las ubicaciones del sitio
    stmt_u = select(Ubicacion).join(Zona, Ubicacion.id_zona == Zona.id).where(
        Zona.id_sitio == sitio.id,
        Ubicacion.id_organizacion == tenant.id_organizacion,
        Ubicacion.activo == True,
    ).order_by(Ubicacion.codigo.asc())
    ubis_all = (await db.execute(stmt_u)).scalars().all()

    # Mapear ubicaciones por zona
    ubis_por_zona: Dict[str, List[LayoutUbicacionNode]] = {}
    for u in ubis_all:
        pct = float((u.ocupacion_actual / u.capacidad_maxima * 100)) if u.capacidad_maxima > 0 else 0.0
        ubis_por_zona.setdefault(u.id_zona, []).append(
            LayoutUbicacionNode(
                id=u.id,
                codigo=u.codigo,
                capacidad_maxima=u.capacidad_maxima,
                ocupacion_actual=u.ocupacion_actual,
                porcentaje_ocupacion=round(pct, 2),
                unidad_capacidad=u.unidad_capacidad,
                estado=u.estado,
                permite_mezcla_lotes=u.permite_mezcla_lotes,
                layout=u.layout or {},
            )
        )

    # Construir jerarquía de zonas
    zonas_map: Dict[str, LayoutZonaNode] = {}
    zonas_raiz: List[LayoutZonaNode] = []

    for z in zonas_all:
        node = LayoutZonaNode(
            id=z.id,
            codigo=z.codigo,
            nombre=z.nombre,
            tipo=z.tipo,
            layout=z.layout or {},
            subzonas=[],
            ubicaciones=ubis_por_zona.get(z.id, []),
        )
        zonas_map[z.id] = node

    for z in zonas_all:
        node = zonas_map[z.id]
        if z.id_zona_padre and z.id_zona_padre in zonas_map:
            zonas_map[z.id_zona_padre].subzonas.append(node)
        else:
            zonas_raiz.append(node)

    return LayoutSitioTree(
        id_sitio=sitio.id,
        codigo=sitio.codigo,
        nombre=sitio.nombre,
        tipo=sitio.tipo,
        zonas=zonas_raiz,
    )


@router.patch("/zonas/{id_zona}")
async def actualizar_layout_zona(
    id_zona: str,
    payload: LayoutUpdate,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Actualiza la posición, rotación o dimensiones espaciales de una zona."""
    stmt = select(Zona).where(
        Zona.id == id_zona,
        Zona.id_organizacion == tenant.id_organizacion,
    )
    zona = (await db.execute(stmt)).scalar_one_or_none()
    if not zona:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zona no encontrada")

    zona.layout = payload.layout
    db.add(
        LogAuditoria(
            id_usuario=tenant.usuario.id,
            accion="LAYOUT_ZONA_ACTUALIZADO",
            entidad_afectada="v2_zona",
            id_entidad=zona.id,
            detalles=payload.layout,
        )
    )
    await db.commit()
    await db.refresh(zona)
    return {"id": zona.id, "codigo": zona.codigo, "layout": zona.layout}


@router.patch("/ubicaciones/{id_ubicacion}")
async def actualizar_layout_ubicacion(
    id_ubicacion: str,
    payload: LayoutUpdate,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Actualiza la posición 2D/3D o dimensiones de una ubicación individual."""
    stmt = select(Ubicacion).where(
        Ubicacion.id == id_ubicacion,
        Ubicacion.id_organizacion == tenant.id_organizacion,
    )
    ubi = (await db.execute(stmt)).scalar_one_or_none()
    if not ubi:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ubicación no encontrada")

    ubi.layout = payload.layout
    db.add(
        LogAuditoria(
            id_usuario=tenant.usuario.id,
            accion="LAYOUT_UBICACION_ACTUALIZADO",
            entidad_afectada="v2_ubicacion",
            id_entidad=ubi.id,
            detalles=payload.layout,
        )
    )
    await db.commit()
    await db.refresh(ubi)
    return {"id": ubi.id, "codigo": ubi.codigo, "layout": ubi.layout}


@router.post("/ubicaciones/batch", status_code=status.HTTP_201_CREATED)
async def crear_ubicaciones_batch(
    payload: UbicacionBatchCreate,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Creación masiva de ubicaciones dentro de una zona para el editor visual
    (por ejemplo, racks completos estructurados por fila, nivel y compartimento).
    """
    stmt_z = select(Zona).where(
        Zona.id == payload.id_zona,
        Zona.id_organizacion == tenant.id_organizacion,
    )
    zona = (await db.execute(stmt_z)).scalar_one_or_none()
    if not zona:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zona destino no encontrada")

    nuevas_ubis = []
    for item in payload.ubicaciones:
        # Verificar duplicado en la zona
        stmt_dup = select(Ubicacion).where(
            Ubicacion.id_zona == zona.id,
            Ubicacion.codigo == item.codigo,
        )
        if (await db.execute(stmt_dup)).scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ya existe una ubicación con el código '{item.codigo}' en esta zona",
            )

        u = Ubicacion(
            id_organizacion=tenant.id_organizacion,
            id_zona=zona.id,
            codigo=item.codigo,
            capacidad_maxima=item.capacidad_maxima,
            unidad_capacidad=item.unidad_capacidad,
            ocupacion_actual=0.0,
            permite_mezcla_lotes=item.permite_mezcla_lotes,
            estado="disponible",
            layout=item.layout,
            atributos={},
            activo=True,
        )
        db.add(u)
        nuevas_ubis.append(u)

    db.add(
        LogAuditoria(
            id_usuario=tenant.usuario.id,
            accion="UBICACIONES_CREADAS_BATCH",
            entidad_afectada="v2_zona",
            id_entidad=zona.id,
            detalles={"cantidad": len(nuevas_ubis)},
        )
    )

    await db.commit()
    return {"id_zona": zona.id, "creadas": len(nuevas_ubis), "codigos": [u.codigo for u in nuevas_ubis]}
