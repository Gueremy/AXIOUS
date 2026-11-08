import uuid
import pytest
from app.core.security import create_access_token
from app.models import Usuario, Sede

@pytest.mark.asyncio
@pytest.mark.parametrize("change", [{"rol":"super_admin"}, {"rol":"gerencia"}, {"id_sede":None}])
async def test_admin_sede_cannot_escalate_or_move_user(client, db, change):
    sede = Sede(id=str(uuid.uuid4()), nombre="Prueba", tipo="bodega", estado="activo")
    db.add(sede)
    await db.flush()
    suffix=uuid.uuid4().hex[:10]
    admin=Usuario(id=str(uuid.uuid4()), nombre="Admin", email=f"a{suffix}@example.cl", password_hash="unused", codigo_empleado=f"A{suffix}", rol="admin_sede", id_sede=sede.id, activo=True)
    user=Usuario(id=str(uuid.uuid4()), nombre="Operario", email=f"o{suffix}@example.cl", password_hash="unused", codigo_empleado=f"O{suffix}", rol="operario", id_sede=sede.id, activo=True)
    db.add_all([admin,user])
    await db.commit()
    headers={"Authorization":f"Bearer {create_access_token({'sub':admin.id})}"}
    response=await client.patch(f"/usuarios/{user.id}", headers=headers, json=change)
    assert response.status_code == 403, response.text
    await db.refresh(user)
    assert user.rol == "operario" and user.id_sede == sede.id
