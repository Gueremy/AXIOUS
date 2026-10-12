"""
tests/v2/test_0d_api_domain.py
Pruebas de integración de la API del nuevo dominio (Fase 0D):
- CRUD y consulta de Sitios, Zonas, Ubicaciones, Ítems y Lotes.
- Paginación y filtrado.
- Jerarquía de zonas y consulta de hijos directos.
- Rechazo estricto cross-tenant (User B recibe 404 al intentar interactuar con recursos de Org A).
"""
import uuid
from decimal import Decimal
import pytest
from httpx import AsyncClient

from app.core.security import create_access_token
from app.models.usuario import Usuario
from app.models.v2 import Organizacion


@pytest.fixture
async def setup_orgs_and_users(db):
    """Fixture que crea dos organizaciones y dos usuarios con tokens JWT válidos."""
    org_a = Organizacion(id=str(uuid.uuid4()), nombre="Empresa A", slug=f"emp-a-{uuid.uuid4().hex[:4]}")
    org_b = Organizacion(id=str(uuid.uuid4()), nombre="Empresa B", slug=f"emp-b-{uuid.uuid4().hex[:4]}")
    db.add_all([org_a, org_b])
    await db.flush()

    user_a = Usuario(
        id=str(uuid.uuid4()),
        nombre="Admin A",
        email=f"admin_a_{uuid.uuid4().hex[:4]}@empa.cl",
        password_hash="fake",
        codigo_empleado="EMP-A-01",
        rol="super_admin",
        id_organizacion=org_a.id,
        activo=True,
    )
    user_b = Usuario(
        id=str(uuid.uuid4()),
        nombre="Admin B",
        email=f"admin_b_{uuid.uuid4().hex[:4]}@empb.cl",
        password_hash="fake",
        codigo_empleado="EMP-B-01",
        rol="super_admin",
        id_organizacion=org_b.id,
        activo=True,
    )
    db.add_all([user_a, user_b])
    await db.flush()

    token_a = create_access_token({"sub": user_a.id, "org_id": org_a.id})
    token_b = create_access_token({"sub": user_b.id, "org_id": org_b.id})

    return {
        "org_a": org_a,
        "org_b": org_b,
        "token_a": token_a,
        "token_b": token_b,
    }


@pytest.mark.asyncio
async def test_flujo_completo_api_dominio_y_aislamiento(client: AsyncClient, setup_orgs_and_users):
    """Prueba el ciclo de vida completo de creación de sitios, zonas, ubicaciones, items y lotes."""
    data = setup_orgs_and_users
    headers_a = {"Authorization": f"Bearer {data['token_a']}"}
    headers_b = {"Authorization": f"Bearer {data['token_b']}"}

    # 1. Crear Sitio en Org A
    resp_sitio = await client.post(
        "/api/v2/sitios/",
        headers=headers_a,
        json={
            "codigo": "SIT-PMO-01",
            "nombre": "Planta Puerto Montt",
            "tipo": "planta",
            "descripcion": "Instalación central",
            "atributos": {"superficie_m2": 2500},
        },
    )
    assert resp_sitio.status_code == 201
    sitio_a_id = resp_sitio.json()["id"]

    # User B no puede ver el sitio de Org A -> 404
    resp_sitio_cross = await client.get(f"/api/v2/sitios/{sitio_a_id}", headers=headers_b)
    assert resp_sitio_cross.status_code == 404

    # 2. Crear Zona Padre y Subzona en Org A
    resp_zona1 = await client.post(
        "/api/v2/zonas/",
        headers=headers_a,
        json={
            "id_sitio": sitio_a_id,
            "codigo": "PATIO-01",
            "nombre": "Patio Logístico",
            "tipo": "patio",
        },
    )
    assert resp_zona1.status_code == 201
    zona1_id = resp_zona1.json()["id"]

    resp_zona2 = await client.post(
        "/api/v2/zonas/",
        headers=headers_a,
        json={
            "id_sitio": sitio_a_id,
            "id_zona_padre": zona1_id,
            "codigo": "BOD-01",
            "nombre": "Bodega Techada",
            "tipo": "bodega",
        },
    )
    assert resp_zona2.status_code == 201
    zona2_id = resp_zona2.json()["id"]

    # Consultar hijos directos de Zona 1
    resp_hijos = await client.get(f"/api/v2/zonas/{zona1_id}/hijos", headers=headers_a)
    assert resp_hijos.status_code == 200
    hijos = resp_hijos.json()
    assert len(hijos) == 1
    assert hijos[0]["id"] == zona2_id

    # 3. Crear Ubicación en Org A
    resp_ubi = await client.post(
        "/api/v2/ubicaciones/",
        headers=headers_a,
        json={
            "id_zona": zona2_id,
            "codigo": "UBI-RACK-01",
            "capacidad_maxima": 1000.0,
            "unidad_capacidad": "kg",
            "permite_mezcla_lotes": False,
        },
    )
    assert resp_ubi.status_code == 201
    ubi_id = resp_ubi.json()["id"]

    # 4. Crear Item en Org A
    resp_item = await client.post(
        "/api/v2/items/",
        headers=headers_a,
        json={
            "codigo": "SKU-HAR-01",
            "nombre": "Harina de Trigo Industrial",
            "categoria": "alimento",
            "unidad_medida": "kg",
        },
    )
    assert resp_item.status_code == 201
    item_id = resp_item.json()["id"]

    # 5. Crear Lote para el Item en Org A
    resp_lote = await client.post(
        "/api/v2/lotes/",
        headers=headers_a,
        json={
            "id_item": item_id,
            "numero_lote": "LOTE-2026-X",
            "estado": "activo",
        },
    )
    assert resp_lote.status_code == 201
    lote_id = resp_lote.json()["id"]

    # 6. User B intenta crear un lote para el item de Org A -> 404
    resp_lote_cross = await client.post(
        "/api/v2/lotes/",
        headers=headers_b,
        json={
            "id_item": item_id,
            "numero_lote": "LOTE-HACK-01",
        },
    )
    assert resp_lote_cross.status_code == 404

    # 7. Listado paginado de Ubicaciones en Org A
    resp_lista_ubi = await client.get("/api/v2/ubicaciones/?page=1&size=10", headers=headers_a)
    assert resp_lista_ubi.status_code == 200
    data_ubi = resp_lista_ubi.json()
    assert data_ubi["total"] == 1
    assert data_ubi["items"][0]["id"] == ubi_id
