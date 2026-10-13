"""La administración v2 no cruza organizaciones ni expone credenciales."""
import uuid

import pytest

from app.core.security import create_access_token, verify_password
from app.models.usuario import Usuario
from app.models.v2 import Organizacion, Sitio


@pytest.mark.asyncio
async def test_administracion_usuarios_v2_aislada(client, db):
    org = Organizacion(id=str(uuid.uuid4()), nombre="Principal", slug=f"main-{uuid.uuid4().hex[:8]}")
    other = Organizacion(id=str(uuid.uuid4()), nombre="Ajena", slug=f"other-{uuid.uuid4().hex[:8]}")
    admin = Usuario(id=str(uuid.uuid4()), nombre="Admin", email=f"admin-{uuid.uuid4().hex[:8]}@example.cl",
                    password_hash="unused", codigo_empleado=f"A-{uuid.uuid4().hex[:10]}",
                    rol="super_admin", id_organizacion=org.id, activo=True)
    db.add_all([org, other, admin])
    await db.flush()
    site = Sitio(id=str(uuid.uuid4()), id_organizacion=org.id, codigo="A", nombre="A", tipo="bodega")
    foreign_site = Sitio(id=str(uuid.uuid4()), id_organizacion=other.id, codigo="B", nombre="B", tipo="bodega")
    db.add_all([site, foreign_site])
    await db.commit()
    headers = {"Authorization": f"Bearer {create_access_token({'sub': admin.id})}"}
    payload = {"nombre": "Operaria", "email": f"op-{uuid.uuid4().hex[:8]}@example.cl",
               "password": "Secret123!", "codigo_empleado": f"O-{uuid.uuid4().hex[:10]}",
               "rol": "operario", "sitios_ids": [site.id]}

    forbidden = await client.post("/api/v2/usuarios", headers=headers,
                                  json={**payload, "sitios_ids": [foreign_site.id]})
    assert forbidden.status_code == 404
    response = await client.post("/api/v2/usuarios", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["sitios_ids"] == [site.id]
    assert "password_hash" not in body and "rut" not in body
    user = await db.get(Usuario, body["id"])
    assert user.id_organizacion == org.id
    assert verify_password(payload["password"], user.password_hash)

    user_headers = {"Authorization": f"Bearer {create_access_token({'sub': user.id})}"}
    assert (await client.get("/api/v2/usuarios", headers=user_headers)).status_code == 403
    assert (await client.post("/auth/register", headers=headers, json=payload)).status_code == 403
    assert {u["id"] for u in (await client.get("/api/v2/usuarios", headers=headers)).json()} == {admin.id, user.id}

    templates = await client.post("/api/v2/roles/plantillas", headers=headers)
    assert templates.status_code == 200, templates.text
    assert len(templates.json()["creadas"]) == 5
    assert (await client.post("/api/v2/roles/plantillas", headers=headers)).json()["creadas"] == []
    custom = await client.post("/api/v2/roles", headers=headers, json={
        "codigo": "auditor_interno", "nombre": "Auditor interno", "permisos": ["dashboard:read"],
    })
    assert custom.status_code == 201, custom.text
    role_id = custom.json()["id"]
    changed = await client.patch(f"/api/v2/roles/{role_id}", headers=headers,
                                 json={"permisos": ["dashboard:read", "reporte:export"]})
    assert changed.status_code == 200
    assert changed.json()["permisos"] == ["dashboard:read", "reporte:export"]
    assigned = await client.patch(f"/api/v2/usuarios/{user.id}", headers=headers,
                                  json={"id_rol_v2": role_id})
    assert assigned.status_code == 200
    assert assigned.json()["id_rol_v2"] == role_id
    assert (await client.get("/api/v2/dashboard/kpis", headers=user_headers)).status_code == 200
