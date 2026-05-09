"""
tests/test_auth.py  — Sprint 1
Verifica: login, token JWT con python-jose 3.3.0, refresh, roles.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import pwd_context
from app.models import Usuario


pytestmark = pytest.mark.asyncio


async def _crear_usuario(db: AsyncSession, rol: str = "operario", sede_id: str = None) -> dict:
    import uuid
    u = Usuario(
        id=str(uuid.uuid4()),
        nombre=f"Test {rol}",
        email=f"{rol}_{uuid.uuid4().hex[:6]}@test.cl",
        password_hash=pwd_context.hash("Test1234!"),
        codigo_empleado=f"T{uuid.uuid4().hex[:6].upper()}",
        rol=rol,
        id_sede=sede_id,
        activo=True,
    )
    db.add(u)
    await db.flush()
    return {"email": u.email, "password": "Test1234!", "id": u.id}


class TestLogin:
    async def test_login_exitoso(self, client: AsyncClient, db: AsyncSession, sede):
        creds = await _crear_usuario(db, sede_id=sede.id)
        r = await client.post("/auth/login", data={"username": creds["email"], "password": creds["password"]})
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    async def test_login_password_incorrecto(self, client: AsyncClient, db: AsyncSession, sede):
        creds = await _crear_usuario(db, sede_id=sede.id)
        r = await client.post("/auth/login", data={"username": creds["email"], "password": "MALO"})
        assert r.status_code == 401

    async def test_login_email_inexistente(self, client: AsyncClient):
        r = await client.post("/auth/login", data={"username": "noexiste@test.cl", "password": "cualquiera"})
        assert r.status_code == 401

    async def test_token_tiene_campos_correctos(self, client: AsyncClient, db: AsyncSession, sede):
        from jose import jwt
        creds = await _crear_usuario(db, sede_id=sede.id)
        r = await client.post("/auth/login", data={"username": creds["email"], "password": creds["password"]})
        assert r.status_code == 200
        token = r.json()["access_token"]
        payload = jwt.decode(token, key="", options={"verify_signature": False}, algorithms=["HS256"])
        assert "sub" in payload
        assert "exp" in payload

    async def test_usuario_inactivo_no_puede_login(self, client: AsyncClient, db: AsyncSession, sede):
        import uuid
        u = Usuario(
            id=str(uuid.uuid4()),
            nombre="Inactivo",
            email="inactivo@test.cl",
            password_hash=pwd_context.hash("Test1234!"),
            codigo_empleado="INACT01",
            rol="operario",
            id_sede=sede.id,
            activo=False,
        )
        db.add(u)
        await db.flush()
        r = await client.post("/auth/login", data={"username": "inactivo@test.cl", "password": "Test1234!"})
        assert r.status_code in (401, 403)


class TestEndpointProtegido:
    async def test_sin_token_retorna_401(self, client: AsyncClient):
        r = await client.get("/containers/")
        assert r.status_code == 401

    async def test_token_invalido_retorna_401(self, client: AsyncClient):
        r = await client.get("/containers/", headers={"Authorization": "Bearer token_invalido"})
        assert r.status_code == 401

    async def test_con_token_valido_accede(self, client: AsyncClient, db: AsyncSession, sede):
        creds = await _crear_usuario(db, sede_id=sede.id)
        login = await client.post("/auth/login", data={"username": creds["email"], "password": creds["password"]})
        token = login.json()["access_token"]
        r = await client.get("/containers/", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
