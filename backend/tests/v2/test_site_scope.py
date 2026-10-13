"""El acceso de usuarios operativos se limita a los sitios asignados."""
import uuid

import pytest

from app.core.security import create_access_token
from app.models.usuario import Usuario
from app.models.v2 import Organizacion, Sitio, Ubicacion, UsuarioSitio, Zona


@pytest.mark.asyncio
async def test_operario_solo_ve_su_sitio_y_no_puede_editar_layout(client, db):
    org = Organizacion(id=str(uuid.uuid4()), nombre="Alcance de sitio", slug=f"scope-{uuid.uuid4().hex[:8]}")
    user = Usuario(
        id=str(uuid.uuid4()), nombre="Operario", email=f"site-{uuid.uuid4().hex[:8]}@example.cl",
        password_hash="unused", codigo_empleado=f"S-{uuid.uuid4().hex[:12]}", rol="operario",
        id_organizacion=org.id, activo=True,
    )
    db.add_all([org, user])
    await db.flush()
    allowed = Sitio(id=str(uuid.uuid4()), id_organizacion=org.id, codigo="A", nombre="Permitido", tipo="bodega")
    denied = Sitio(id=str(uuid.uuid4()), id_organizacion=org.id, codigo="B", nombre="Restringido", tipo="bodega")
    db.add_all([allowed, denied])
    await db.flush()
    zone_a = Zona(id=str(uuid.uuid4()), id_organizacion=org.id, id_sitio=allowed.id, codigo="ZA", nombre="ZA", tipo="zona")
    zone_b = Zona(id=str(uuid.uuid4()), id_organizacion=org.id, id_sitio=denied.id, codigo="ZB", nombre="ZB", tipo="zona")
    db.add_all([zone_a, zone_b, UsuarioSitio(id_usuario=user.id, id_sitio=allowed.id)])
    await db.flush()
    location_b = Ubicacion(id=str(uuid.uuid4()), id_organizacion=org.id, id_zona=zone_b.id,
                           codigo="LB", capacidad_maxima=100, unidad_capacidad="kg")
    db.add(location_b)
    await db.commit()

    headers = {"Authorization": f"Bearer {create_access_token({'sub': user.id})}"}
    assert [s["id"] for s in (await client.get("/api/v2/sitios/", headers=headers)).json()["items"]] == [allowed.id]
    assert [z["id"] for z in (await client.get("/api/v2/zonas/", headers=headers)).json()["items"]] == [zone_a.id]
    assert (await client.get(f"/api/v2/ubicaciones/{location_b.id}", headers=headers)).status_code == 403
    assert (await client.patch(f"/api/v2/layout/ubicaciones/{location_b.id}", headers=headers,
                               json={"layout": {"x": 5}})).status_code == 403
    assert (await client.get(f"/api/v2/layout/sitios/{denied.id}", headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_operario_sin_sitio_asignado_no_gana_acceso_global(client, db):
    org = Organizacion(id=str(uuid.uuid4()), nombre="Sin asignación", slug=f"empty-{uuid.uuid4().hex[:8]}")
    user = Usuario(
        id=str(uuid.uuid4()), nombre="Sin sitio", email=f"empty-{uuid.uuid4().hex[:8]}@example.cl",
        password_hash="unused", codigo_empleado=f"E-{uuid.uuid4().hex[:12]}", rol="operario",
        id_organizacion=org.id, activo=True,
    )
    site = Sitio(id=str(uuid.uuid4()), id_organizacion=org.id, codigo="S", nombre="Sitio", tipo="bodega")
    db.add_all([org, user, site])
    await db.commit()
    headers = {"Authorization": f"Bearer {create_access_token({'sub': user.id})}"}
    assert (await client.get("/api/v2/sitios/", headers=headers)).json()["items"] == []
    assert (await client.get(f"/api/v2/sitios/{site.id}", headers=headers)).status_code == 403
