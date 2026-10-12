"""
tests/v2/test_0c_tenant_isolation.py
Pruebas automatizadas de la Fase 0C:
- Aislamiento estricto multi-organización (cross-tenant security).
- Resolución central del tenant (dependencies_v2.py).
- Restricciones granulares de acceso por sitio.
- Roles configurables y validación de permisos RBAC.
- Blindaje de cuentas y organizaciones desactivadas.
"""
import uuid
import pytest
from fastapi import HTTPException

from app.core.dependencies_v2 import TenantContext, PLANTILLAS_PERMISOS
from app.models.usuario import Usuario
from app.models.v2 import (
    Organizacion, Sitio, UsuarioSitio, Rol, Permiso, RolPermiso
)


@pytest.fixture
def org_a():
    return Organizacion(
        id=str(uuid.uuid4()),
        nombre="Organización Austral",
        slug="austral-test",
        activo=True,
    )


@pytest.fixture
def org_b():
    return Organizacion(
        id=str(uuid.uuid4()),
        nombre="Organización Central",
        slug="central-test",
        activo=True,
    )


@pytest.fixture
def user_a(org_a):
    return Usuario(
        id=str(uuid.uuid4()),
        nombre="Operario Austral",
        email="operario@austral.cl",
        password_hash="hash",
        codigo_empleado="EMP-AUS-01",
        rol="operario",
        id_organizacion=org_a.id,
        activo=True,
    )


@pytest.fixture
def user_b(org_b):
    return Usuario(
        id=str(uuid.uuid4()),
        nombre="Jefe Central",
        email="jefe@central.cl",
        password_hash="hash",
        codigo_empleado="EMP-CEN-01",
        rol="jefe_bodega",
        id_organizacion=org_b.id,
        activo=True,
    )


def test_tenant_context_rechaza_recurso_de_otra_organizacion(org_a, org_b, user_a):
    """Verifica que un usuario de Org A no puede acceder a recursos de Org B (retorna 404 para evitar inferencia)."""
    context_a = TenantContext(
        usuario=user_a,
        organizacion=org_a,
        rol_codigo="operario",
        permisos=PLANTILLAS_PERMISOS["operario"],
        sitios_permitidos=None,
    )

    # Recurso de su propia organización -> pasa
    context_a.validar_pertenencia_org(org_a.id)

    # Recurso de Org B -> lanza 404
    with pytest.raises(HTTPException) as exc:
        context_a.validar_pertenencia_org(org_b.id)
    assert exc.value.status_code == 404
    assert "no encontrado" in exc.value.detail.lower()


def test_rbac_permisos_por_rol(org_a, user_a):
    """Verifica la asignación correcta de permisos y la distinción entre operario y super_admin."""
    context_operario = TenantContext(
        usuario=user_a,
        organizacion=org_a,
        rol_codigo="operario",
        permisos=PLANTILLAS_PERMISOS["operario"],
        sitios_permitidos=None,
    )

    # Operario puede consultar items pero no borrar sitios
    assert context_operario.tiene_permiso("item:read") is True
    assert context_operario.tiene_permiso("sitio:delete") is False

    # Super admin de la org tiene permiso total dentro de su org
    context_admin = TenantContext(
        usuario=user_a,
        organizacion=org_a,
        rol_codigo="super_admin",
        permisos=PLANTILLAS_PERMISOS["super_admin"],
        sitios_permitidos=None,
    )
    assert context_admin.tiene_permiso("sitio:delete") is True
    assert context_admin.tiene_permiso("cualquier_cosa:custom") is True


def test_restriccion_acceso_por_sitio(org_a, user_a):
    """Verifica que un usuario limitado a sitios específicos no puede operar en otros sitios de su misma org."""
    sitio_permitido_id = str(uuid.uuid4())
    sitio_bloqueado_id = str(uuid.uuid4())

    context = TenantContext(
        usuario=user_a,
        organizacion=org_a,
        rol_codigo="operario",
        permisos=PLANTILLAS_PERMISOS["operario"],
        sitios_permitidos={sitio_permitido_id},
    )

    assert context.puede_acceder_sitio(sitio_permitido_id) is True
    assert context.puede_acceder_sitio(sitio_bloqueado_id) is False


def test_super_admin_accede_a_todos_los_sitios_de_su_org(org_a, user_a):
    """Un super_admin de la organización no sufre restricción de sitios dentro de su empresa."""
    sitio_aleatorio_id = str(uuid.uuid4())

    context = TenantContext(
        usuario=user_a,
        organizacion=org_a,
        rol_codigo="super_admin",
        permisos=PLANTILLAS_PERMISOS["super_admin"],
        sitios_permitidos={str(uuid.uuid4())},  # asignación irrelevante para super_admin
    )

    assert context.puede_acceder_sitio(sitio_aleatorio_id) is True
