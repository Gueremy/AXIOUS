from typing import Any, Dict, List, Optional
import ipaddress
from urllib.parse import urlsplit
from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies_v2 import TenantContext, get_current_tenant
from app.core.audit import log_action
from app.core.events.event_bus import DomainEvent, EventBus
from app.database import get_db
from app.integraciones.registry import ConectorRegistry
from app.models.log_auditoria import LogAuditoria
from app.models.v2.webhook import WebhookDestino, WebhookEntrega
from app.models.v2.evento_entrante import EventoEntranteRegistrado
from app.integraciones.webhooks import cifrar_secreto

router = APIRouter(prefix="/integraciones", tags=["V2 - Integraciones y Webhooks"])


class EventoEntrante(BaseModel):
    id_evento_externo: Optional[str] = Field(None, max_length=150, description="UUID o ID externo para idempotencia")
    tipo_evento: str = Field(..., pattern=r"^[a-zA-Z0-9_.-]{1,100}$", description="ej: stock.updated, movimiento.sync, rfid.read")
    datos: Dict[str, Any] = Field(default_factory=dict)


class ConectorTestRequest(BaseModel):
    configuracion: Dict[str, Any]


class WebhookCreate(BaseModel):
    url: str = Field(..., max_length=2048)
    secreto: str = Field(..., min_length=16, max_length=512)
    eventos: List[str] = Field(..., min_length=1)


class WebhookUpdate(BaseModel):
    activo: Optional[bool] = None
    secreto: Optional[str] = Field(None, min_length=16, max_length=512)
    eventos: Optional[List[str]] = None


def _validar_webhook_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(status_code=400, detail="URL de webhook inválida")
    if parsed.scheme != "https":
        raise HTTPException(status_code=400, detail="El webhook requiere HTTPS")
    host = parsed.hostname.lower()
    if host == "localhost" or host.endswith(".localhost"):
        raise HTTPException(status_code=400, detail="Destino local no permitido")
    try:
        address = ipaddress.ip_address(host)
        if not address.is_global:
            raise HTTPException(status_code=400, detail="Destino privado no permitido")
    except ValueError:
        pass


def _validar_eventos(eventos: List[str]) -> None:
    if not eventos or any(e not in {"movimiento.creado", "movimiento.rechazado"} for e in eventos):
        raise HTTPException(status_code=400, detail="Evento webhook no soportado")


def _webhook_publico(destino: WebhookDestino) -> Dict[str, Any]:
    return {"id": destino.id, "url": destino.url, "eventos": destino.eventos, "activo": destino.activo}


@router.get("/webhooks")
async def listar_webhooks(tenant: TenantContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)):
    if not tenant.tiene_permiso("rbac:manage"):
        raise HTTPException(status_code=403, detail="Permiso insuficiente")
    destinos = (await db.execute(select(WebhookDestino).where(
        WebhookDestino.id_organizacion == tenant.id_organizacion,
    ))).scalars().all()
    return [_webhook_publico(destino) for destino in destinos]


@router.post("/webhooks", status_code=status.HTTP_201_CREATED)
async def crear_webhook(data: WebhookCreate, tenant: TenantContext = Depends(get_current_tenant),
                        db: AsyncSession = Depends(get_db)):
    if not tenant.tiene_permiso("rbac:manage"):
        raise HTTPException(status_code=403, detail="Permiso insuficiente")
    _validar_webhook_url(data.url)
    _validar_eventos(data.eventos)
    if (await db.execute(select(WebhookDestino.id).where(
        WebhookDestino.id_organizacion == tenant.id_organizacion,
        WebhookDestino.url == data.url,
    ))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="El destino ya está registrado")
    destino = WebhookDestino(id_organizacion=tenant.id_organizacion, url=data.url,
                             secreto_cifrado=cifrar_secreto(data.secreto), eventos=data.eventos, activo=True)
    db.add(destino)
    await db.flush()
    await log_action(db, tenant.usuario.id, "CREAR_WEBHOOK_V2", "v2_webhook_destino",
                     destino.id, {"id_organizacion": tenant.id_organizacion, "url": destino.url,
                                  "eventos": destino.eventos})
    await db.commit()
    await db.refresh(destino)
    return _webhook_publico(destino)


@router.patch("/webhooks/{id_destino}")
async def actualizar_webhook(id_destino: str, data: WebhookUpdate,
                             tenant: TenantContext = Depends(get_current_tenant), db: AsyncSession = Depends(get_db)):
    if not tenant.tiene_permiso("rbac:manage"):
        raise HTTPException(status_code=403, detail="Permiso insuficiente")
    destino = (await db.execute(select(WebhookDestino).where(
        WebhookDestino.id == id_destino, WebhookDestino.id_organizacion == tenant.id_organizacion,
    ))).scalar_one_or_none()
    if not destino:
        raise HTTPException(status_code=404, detail="Destino no encontrado")
    if data.eventos is not None:
        _validar_eventos(data.eventos)
        destino.eventos = data.eventos
    if data.secreto is not None:
        destino.secreto_cifrado = cifrar_secreto(data.secreto)
    if data.activo is not None:
        destino.activo = data.activo
    await log_action(db, tenant.usuario.id, "ACTUALIZAR_WEBHOOK_V2", "v2_webhook_destino",
                     destino.id, {"id_organizacion": tenant.id_organizacion,
                                  "campos": sorted(data.model_fields_set)})
    await db.commit()
    return _webhook_publico(destino)


@router.get("/webhooks/entregas")
async def listar_entregas_webhook(tenant: TenantContext = Depends(get_current_tenant),
                                 db: AsyncSession = Depends(get_db)):
    if not tenant.tiene_permiso("rbac:manage"):
        raise HTTPException(status_code=403, detail="Permiso insuficiente")
    entregas = (await db.execute(select(WebhookEntrega).where(
        WebhookEntrega.id_organizacion == tenant.id_organizacion,
    ).order_by(WebhookEntrega.fecha_creacion.desc()).limit(100))).scalars().all()
    return [{"id": e.id, "id_destino": e.id_destino, "tipo_evento": e.tipo_evento,
             "id_evento": e.id_evento, "estado": e.estado, "intentos": e.intentos} for e in entregas]


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
    if not tenant.tiene_permiso("rbac:manage"):
        raise HTTPException(status_code=403, detail="Permiso insuficiente")
    conector = ConectorRegistry.obtener(id_conector)
    if not conector:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conector no encontrado")

    ok = conector.probar_conexion(payload.configuracion)
    return {"id_conector": id_conector, "conexion_exitosa": ok}


@router.post("/{fuente}/eventos", status_code=status.HTTP_202_ACCEPTED)
async def recibir_evento_externo(
    payload: EventoEntrante,
    fuente: str = Path(..., pattern=r"^[a-zA-Z0-9_-]{1,100}$"),
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Entrada genérica de eventos para sistemas externos (ERP, WMS, básculas, RFID, sensores).
    Despacha el evento al Bus de Eventos interno de SalmoTrack v2.
    """
    if not tenant.tiene_permiso("rbac:manage"):
        raise HTTPException(status_code=403, detail="Permiso insuficiente")
    event_name = f"integracion.{fuente}.{payload.tipo_evento}"

    if payload.id_evento_externo:
        existing = (await db.execute(select(EventoEntranteRegistrado).where(
            EventoEntranteRegistrado.id_organizacion == tenant.id_organizacion,
            EventoEntranteRegistrado.fuente == fuente,
            EventoEntranteRegistrado.id_evento_externo == payload.id_evento_externo,
        ))).scalar_one_or_none()
        if existing:
            if existing.tipo_evento != payload.tipo_evento:
                raise HTTPException(status_code=409, detail="El ID externo ya corresponde a otro tipo de evento")
            return {"status": "duplicate", "fuente": fuente, "evento": event_name,
                    "id_organizacion": tenant.id_organizacion}
        try:
            async with db.begin_nested():
                db.add(EventoEntranteRegistrado(
                    id_organizacion=tenant.id_organizacion, fuente=fuente,
                    id_evento_externo=payload.id_evento_externo, tipo_evento=payload.tipo_evento,
                ))
                await db.flush()
        except IntegrityError:
            return {"status": "duplicate", "fuente": fuente, "evento": event_name,
                    "id_organizacion": tenant.id_organizacion}

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
