"""La clave externa impide publicar el mismo evento dos veces."""
import uuid

import pytest

from app.core.events.event_bus import EventBus
from app.core.security import create_access_token
from app.models.usuario import Usuario
from app.models.v2 import Organizacion


@pytest.mark.asyncio
async def test_evento_externo_idempotente_por_organizacion_y_fuente(client, db):
    org = Organizacion(id=str(uuid.uuid4()), nombre="Eventos", slug=f"evt-{uuid.uuid4().hex[:8]}")
    user = Usuario(id=str(uuid.uuid4()), nombre="Admin", email=f"evt-{uuid.uuid4().hex[:8]}@example.cl",
                   password_hash="unused", codigo_empleado=f"E-{uuid.uuid4().hex[:10]}",
                   rol="super_admin", id_organizacion=org.id, activo=True)
    db.add_all([org, user])
    await db.commit()
    events = []
    def capture(event):
        events.append(event)
    EventBus.subscribe("integracion.erp.stock.updated", capture)
    headers = {"Authorization": f"Bearer {create_access_token({'sub': user.id})}"}
    payload = {"id_evento_externo": "externo-1", "tipo_evento": "stock.updated", "datos": {"cantidad": 4}}
    try:
        first = await client.post("/api/v2/integraciones/erp/eventos", json=payload, headers=headers)
        repeat = await client.post("/api/v2/integraciones/erp/eventos", json=payload, headers=headers)
        assert first.status_code == repeat.status_code == 202
        assert first.json()["status"] == "accepted"
        assert repeat.json()["status"] == "duplicate"
        assert len(events) == 1
        conflict = await client.post("/api/v2/integraciones/erp/eventos", headers=headers,
                                     json={**payload, "tipo_evento": "stock.deleted"})
        assert conflict.status_code == 409
    finally:
        EventBus._subscribers["integracion.erp.stock.updated"].remove(capture)
