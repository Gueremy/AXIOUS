"""Checks the real PostgreSQL login rather than relying on HTTP tenant filtering."""
import uuid
import pytest
import psycopg2
from psycopg2 import sql
from app.core.config import settings
from scripts.provision_bi import provision


def test_bi_login_only_reads_its_organization():
    if "axious_v2_completion_test" not in settings.DATABASE_URL_SYNC:
        pytest.skip("Requiere PostgreSQL aislado axious_v2_completion_test migrado")
    url = settings.DATABASE_URL_SYNC.replace("postgresql+psycopg2://", "postgresql://")
    organizations = [str(uuid.uuid4()), str(uuid.uuid4())]
    role = None
    with psycopg2.connect(url) as admin:
        try:
            with admin.cursor() as cursor:
                for index, org in enumerate(organizations):
                    cursor.execute("INSERT INTO v2_organizacion(id,nombre,slug,configuracion,activo) VALUES(%s,%s,%s,'{}',true)", (org, "BI prueba", "bi-" + org))
                    cursor.execute("INSERT INTO v2_sitio(id,id_organizacion,codigo,nombre,tipo,atributos,activo) VALUES(%s,%s,%s,%s,'bodega','{}',true)", (str(uuid.uuid4()), org, f"SITE-{index}", "Bodega prueba"))
            admin.commit()
            role = provision(organizations[0], "bi-test-only-password-123")
            parameters = admin.get_dsn_parameters()
            parameters = {key: parameters[key] for key in ("host", "port", "dbname") if key in parameters}
            with psycopg2.connect(**parameters, user=role, password="bi-test-only-password-123") as reader:
                with reader.cursor() as cursor:
                    cursor.execute("SELECT codigo FROM salmotrack_bi.sitios")
                    assert cursor.fetchall() == [("SITE-0",)]
                    cursor.execute("SET salmotrack.organization_id = %s", (organizations[1],))
                    cursor.execute("SELECT codigo FROM salmotrack_bi.sitios")
                    assert cursor.fetchall() == [("SITE-0",)]
                    reader.rollback()
                    # Read-only defaults are mutable by the client. The actual grants
                    # must still deny writes after that convenience setting is disabled.
                    reader.autocommit = True
                    cursor.execute("SET default_transaction_read_only = off")
                    for forbidden in ("SELECT * FROM public.usuario", "SELECT * FROM salmotrack_bi.principal", "DELETE FROM salmotrack_bi.sitios"):
                        with pytest.raises(psycopg2.Error):
                            cursor.execute(forbidden)
                        reader.rollback()
        finally:
            admin.rollback()
            with admin.cursor() as cursor:
                if role:
                    cursor.execute("DELETE FROM salmotrack_bi.principal WHERE login_name=%s", (role,))
                    cursor.execute(sql.SQL("DROP OWNED BY {}").format(sql.Identifier(role)))
                    cursor.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
                for org in organizations:
                    cursor.execute("DELETE FROM v2_sitio WHERE id_organizacion=%s", (org,))
                    cursor.execute("DELETE FROM v2_organizacion WHERE id=%s", (org,))
