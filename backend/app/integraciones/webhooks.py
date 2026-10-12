"""
app/integraciones/webhooks.py
Emisor de webhooks salientes con firma HMAC-SHA256 (Fase 4).
Protege secretos (nunca los expone en logs).
"""
import hashlib
import hmac
import json
import logging
from typing import Any, Dict
import httpx

logger = logging.getLogger("app.webhooks")


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
            logger.error(f"Error al despachar webhook hacia {url}: {exc}")
            return False
