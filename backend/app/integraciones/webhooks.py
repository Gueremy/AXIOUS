"""
app/integraciones/webhooks.py
Emisor de webhooks salientes con firma HMAC-SHA256 (Fase 4).
Protege secretos (nunca los expone en logs).
"""
import hashlib
import hmac
import json
import logging
import base64
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict
import httpx
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.core.config import settings
from app.core.events.event_bus import DomainEvent
from app.database import AsyncSessionLocal
from app.models.v2.webhook import WebhookDestino, WebhookEntrega

logger = logging.getLogger("app.webhooks")


def _cipher() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest())
    return Fernet(key)


def cifrar_secreto(secret: str) -> str:
    return _cipher().encrypt(secret.encode("utf-8")).decode("ascii")


def descifrar_secreto(ciphertext: str) -> str:
    return _cipher().decrypt(ciphertext.encode("ascii")).decode("utf-8")


def firmar_payload(payload_bytes: bytes, secret: str) -> str:
    """Calcula la firma HMAC-SHA256 del payload utilizando el secreto configurado."""
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()


class WebhookDispatcher:

    @staticmethod
    async def despachar(
        url: str,
        secret: str,
        evento: Dict[str, Any],
    ) -> bool:
        """
        Envía un payload de evento vía HTTP POST con encabezado de firma 'X-SalmoTrack-Signature'.
        """
        payload_bytes = json.dumps(evento, default=str).encode("utf-8")
        signature = firmar_payload(payload_bytes, secret)

        headers = {
            "Content-Type": "application/json",
            "X-SalmoTrack-Signature": f"sha256={signature}",
            "User-Agent": "SalmoTrack-Webhook/2.0",
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, content=payload_bytes, headers=headers)
                return resp.is_success
        except Exception as exc:
            logger.warning("Error al despachar webhook: %s", type(exc).__name__)
            return False


async def encolar_evento_webhook(event: DomainEvent) -> None:
    """Persiste una entrega por destino tras confirmarse el evento de dominio."""
    event_id = str(event.payload.get("id_movimiento") or event.payload.get("id_solicitud") or event.payload.get("id_job") or uuid.uuid4())
    if event.name == "movimiento.etapa_aprobada":
        event_id = f"{event_id}:{event.payload.get('etapa')}"
    async with AsyncSessionLocal() as db:
        destinos = (await db.execute(select(WebhookDestino).where(
            WebhookDestino.id_organizacion == event.id_organizacion,
            WebhookDestino.activo == True,
        ))).scalars().all()
        for destino in destinos:
            if event.name not in destino.eventos:
                continue
            existe = (await db.execute(select(WebhookEntrega.id).where(
                WebhookEntrega.id_destino == destino.id,
                WebhookEntrega.tipo_evento == event.name,
                WebhookEntrega.id_evento == event_id,
            ))).scalar_one_or_none()
            if existe:
                continue
            db.add(WebhookEntrega(
                id_organizacion=event.id_organizacion, id_destino=destino.id,
                tipo_evento=event.name, id_evento=event_id,
                payload={"evento": event.name, "id_evento": event_id,
                         "fecha": event.timestamp.isoformat(), "datos": event.payload},
                estado="pendiente", intentos=0,
                proximo_intento=datetime.now(timezone.utc),
            ))
        await db.commit()


async def despachar_webhooks_pendientes() -> None:
    """Reintenta entregas fallidas con espera exponencial y máximo cinco intentos."""
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        entregas = (await db.execute(select(WebhookEntrega).where(
            WebhookEntrega.estado == "pendiente",
            WebhookEntrega.proximo_intento <= now,
        ).order_by(WebhookEntrega.proximo_intento.asc()).limit(10).with_for_update(skip_locked=True))).scalars().all()
        for entrega in entregas:
            destino = (await db.execute(select(WebhookDestino).where(
                WebhookDestino.id == entrega.id_destino,
                WebhookDestino.id_organizacion == entrega.id_organizacion,
            ))).scalar_one_or_none()
            if not destino or not destino.activo:
                entrega.estado = "cancelado"
                continue
            try:
                ok = await WebhookDispatcher.despachar(
                    destino.url, descifrar_secreto(destino.secreto_cifrado), entrega.payload,
                )
            except Exception as exc:
                logger.warning("No se pudo preparar una entrega webhook: %s", type(exc).__name__)
                ok = False
            entrega.intentos += 1
            if ok:
                entrega.estado = "enviado"
                entrega.fecha_envio = datetime.now(timezone.utc)
            elif entrega.intentos >= 5:
                entrega.estado = "fallido"
            else:
                entrega.proximo_intento = datetime.now(timezone.utc) + timedelta(minutes=min(2 ** entrega.intentos, 60))
        await db.commit()
