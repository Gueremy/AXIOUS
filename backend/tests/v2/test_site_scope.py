"""El acceso de usuarios operativos se limita a los sitios asignados."""
import uuid

import pytest

from app.core.security import create_access_token
from app.models.usuario import Usuario
from app.models.v2 import Organizacion, Sitio, Ubicacion, UsuarioSitio, Zona
from app.models.v2.alerta import AlertaV2
from app.models.v2.item import Item
from app.models.v2.saldo_stock import SaldoStock


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
    assert (await client.get("/sedes/", headers=headers)).status_code == 403


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


@pytest.mark.asyncio
async def test_reportes_alertas_y_picking_respetan_asignacion_sitio(client, db):
    org = Organizacion(id=str(uuid.uuid4()), nombre="Dos sedes", slug=f"scope-{uuid.uuid4().hex[:8]}")
    user = Usuario(id=str(uuid.uuid4()), nombre="Jefe", email=f"boss-{uuid.uuid4().hex[:8]}@example.cl",
                   password_hash="unused", codigo_empleado=f"J-{uuid.uuid4().hex[:12]}",
                   rol="jefe_bodega", id_organizacion=org.id, activo=True)
    db.add_all([org, user])
    await db.flush()
    sites = [Sitio(id=str(uuid.uuid4()), id_organizacion=org.id, codigo=c, nombre=c, tipo="bodega")
             for c in ("A", "B")]
    db.add_all(sites)
    await db.flush()
    zones = [Zona(id=str(uuid.uuid4()), id_organizacion=org.id, id_sitio=s.id,
                  codigo=f"Z{s.codigo}", nombre=f"Z{s.codigo}", tipo="zona") for s in sites]
    db.add_all(zones)
    db.add(UsuarioSitio(id_usuario=user.id, id_sitio=sites[0].id))
    await db.flush()
    locations = [Ubicacion(id=str(uuid.uuid4()), id_organizacion=org.id, id_zona=z.id,
                           codigo=f"L{i}", capacidad_maxima=100, ocupacion_actual=10,
                           unidad_capacidad="kg") for i, z in enumerate(zones)]
    item = Item(id=str(uuid.uuid4()), id_organizacion=org.id, codigo="SKU", nombre="Producto",
                categoria="general", unidad_medida="kg")
    db.add_all([*locations, item])
    await db.flush()
    db.add_all([SaldoStock(id_organizacion=org.id, id_ubicacion=loc.id, id_item=item.id,
                           cantidad=10, unidad_medida="kg") for loc in locations])
    db.add_all([AlertaV2(id_organizacion=org.id, id_sitio=s.id, id_ubicacion=loc.id,
                         tipo="capacidad", severidad="aviso", titulo="Capacidad",
                         descripcion="Prueba", estado="activa") for s, loc in zip(sites, locations)])
    await db.commit()
    headers = {"Authorization": f"Bearer {create_access_token({'sub': user.id})}"}

    kpis = (await client.get("/api/v2/dashboard/kpis", headers=headers)).json()
    assert kpis["total_ubicaciones"] == 1
    assert float(kpis["stock_total"]) == 10
    assert len((await client.get("/api/v2/dashboard/ocupacion", headers=headers)).json()) == 1
    assert len((await client.get("/api/v2/bi/hechos/stock", headers=headers)).json()) == 1
    assert len((await client.get("/api/v2/bi/dimensiones/sitios", headers=headers)).json()) == 1
    assert len((await client.get("/api/v2/alertas/activas", headers=headers)).json()) == 1
    picking = (await client.get(f"/api/v2/picking/sugerir?id_item={item.id}&cantidad=15", headers=headers)).json()
    assert float(picking["cantidad_asignada"]) == 10
    assert [s["id_ubicacion"] for s in picking["sugerencias"]] == [locations[0].id]
