from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies_v2 import TenantContext, get_current_tenant
from app.core.events.event_bus import DomainEvent, EventBus
from app.database import get_db
from app.integraciones.registry import ConectorRegistry
from app.models.log_auditoria import LogAuditoria

router = APIRouter(prefix="/integraciones", tags=["V2 - Integraciones y Webhooks"])


class EventoEntrante(BaseModel):
    id_evento_externo: Optional[str] = Field(None, description="UUID o ID externo para idempotencia")
    tipo_evento: str = Field(..., description="ej: stock.updated, movimiento.sync, rfid.read")
    datos: Dict[str, Any] = Field(default_factory=dict)


class ConectorTestRequest(BaseModel):
    configuracion: Dict[str, Any]


@router.get("/conectores")
async def listar_conectores(tenant: TenantContext = Depends(get_current_tenant)):
    """Lista los conectores disponibles en el registro central."""
    return ConectorRegistry.listar()


@router.post("/conectores/{id_conector}/probar")
async def probar_conector(
    id_conector: str,
    payload: ConectorTestRequest,
    tenant: TenantContext = Depends(get_current_tenant),
):
    """Prueba la conectividad de un conector con los parámetros suministrados."""
    conector = ConectorRegistry.obtener(id_conector)
    if not conector:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conector no encontrado")

    ok = conector.probar_conexion(payload.configuracion)
    return {"id_conector": id_conector, "conexion_exitosa": ok}


@router.post("/{fuente}/eventos", status_code=status.HTTP_202_ACCEPTED)
async def recibir_evento_externo(
    fuente: str,
    payload: EventoEntrante,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Entrada genérica de eventos para sistemas externos (ERP, WMS, básculas, RFID, sensores).
    Despacha el evento al Bus de Eventos interno de SalmoTrack v2.
    """
    event_name = f"integracion.{fuente}.{payload.tipo_evento}"

    db.add(
        LogAuditoria(
            id_usuario=tenant.usuario.id,
            accion="EVENTO_EXTERNO_RECIBIDO",
            entidad_afectada=f"integracion:{fuente}",
            id_entidad=payload.id_evento_externo,
            detalles={"fuente": fuente, "tipo_evento": payload.tipo_evento},
        )
    )
    await db.commit()

    await EventBus.publish(
        DomainEvent(
            name=event_name,
            id_organizacion=tenant.id_organizacion,
            payload={
                "fuente": fuente,
                "id_evento_externo": payload.id_evento_externo,
                "datos": payload.datos,
            },
        )
    )

    return {
        "status": "accepted",
        "fuente": fuente,
        "evento": event_name,
        "id_organizacion": tenant.id_organizacion,
    }
