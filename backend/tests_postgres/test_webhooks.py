"""Entrega firmada y reintentos durables sobre PostgreSQL."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.core.events.event_bus import DomainEvent
from app.database import AsyncSessionLocal
from app.integraciones.webhooks import (
    WebhookDispatcher, cifrar_secreto, descifrar_secreto,
    despachar_webhooks_pendientes, encolar_evento_webhook,
)
from app.models.v2 import Organizacion, WebhookDestino, WebhookEntrega


@pytest.mark.asyncio(loop_scope="session")
async def test_webhook_encrypted_queue_and_retry(monkeypatch):
    if "postgresql+asyncpg" not in settings.DATABASE_URL or "axious_v2_completion_test" not in settings.DATABASE_URL:
        pytest.skip("Requiere DATABASE_URL de PostgreSQL axious_v2_completion_test")

    org = Organizacion(id=str(uuid.uuid4()), nombre="Webhook Test", slug=f"hook-{uuid.uuid4().hex[:12]}")
    secret = "test-secret-only-in-memory-123456"
    destino = WebhookDestino(id_organizacion=org.id, url="https://example.com/hooks",
                             secreto_cifrado=cifrar_secreto(secret), eventos=["movimiento.creado"], activo=True)
    assert destino.secreto_cifrado != secret
    assert descifrar_secreto(destino.secreto_cifrado) == secret
    async with AsyncSessionLocal() as db:
        db.add(org)
        await db.flush()
        db.add(destino)
        await db.commit()

    event_id = str(uuid.uuid4())
    event = DomainEvent("movimiento.creado", org.id, {"id_movimiento": event_id})
    await encolar_evento_webhook(event)
    await encolar_evento_webhook(event)
    async with AsyncSessionLocal() as db:
        queued = (await db.execute(select(WebhookEntrega).where(
            WebhookEntrega.id_destino == destino.id,
        ))).scalars().all()
        assert len(queued) == 1
        assert queued[0].estado == "pendiente"

    attempts = []

    async def fake_dispatch(url, provided_secret, payload):
        attempts.append((url, provided_secret, payload["id_evento"]))
        return len(attempts) >= 2

    monkeypatch.setattr(WebhookDispatcher, "despachar", staticmethod(fake_dispatch))
    await despachar_webhooks_pendientes()
    async with AsyncSessionLocal() as db:
        delivery = (await db.execute(select(WebhookEntrega).where(
            WebhookEntrega.id_destino == destino.id,
        ))).scalar_one()
        assert delivery.estado == "pendiente" and delivery.intentos == 1
        delivery.proximo_intento = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()

    await despachar_webhooks_pendientes()
    async with AsyncSessionLocal() as db:
        delivery = (await db.execute(select(WebhookEntrega).where(
            WebhookEntrega.id_destino == destino.id,
        ))).scalar_one()
        assert delivery.estado == "enviado" and delivery.intentos == 2
        assert attempts == [("https://example.com/hooks", secret, event_id)] * 2
