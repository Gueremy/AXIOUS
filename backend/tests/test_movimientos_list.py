import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.usuario import Usuario


pytestmark = pytest.mark.asyncio


async def _login(client: AsyncClient, email: str, password: str) -> str:
    response = await client.post("/auth/login", data={"username": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def test_lista_movimientos_enriquecida(
    client: AsyncClient,
    db: AsyncSession,
    movimiento_aprobado,
    usuario_jefe: Usuario,
):
    token = await _login(client, usuario_jefe.email, "Test1234!")

    response = await client.get(
        "/movimientos/",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] >= 1
    item = data["items"][0]
    assert "producto_nombre" in item
    assert "container_codigo" in item
    assert "operario_nombre" in item
    assert item["numero_lote"] == movimiento_aprobado.numero_lote


async def test_lista_movimientos_filtra_por_busqueda(
    client: AsyncClient,
    db: AsyncSession,
    movimiento_aprobado,
    usuario_jefe: Usuario,
):
    token = await _login(client, usuario_jefe.email, "Test1234!")

    response = await client.get(
        f"/movimientos/?q={movimiento_aprobado.numero_lote}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] >= 1
    assert all(item["numero_lote"] == movimiento_aprobado.numero_lote for item in data["items"])
