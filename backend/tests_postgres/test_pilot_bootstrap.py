"""Pilot startup under the non-superuser privileges used by managed PostgreSQL."""
import os
import subprocess
import sys
import uuid
from contextlib import closing

import psycopg2
from psycopg2 import sql
import pytest
from app.core.config import settings
from scripts.bootstrap_pilot_bi import bootstrap, verify_reader, PILOT_ID


def test_pilot_bootstrap_with_database_owner_without_superuser():
    if "axious_v2_completion_test" not in settings.DATABASE_URL_SYNC:
        pytest.skip("Requires isolated PostgreSQL test database")
    url = settings.DATABASE_URL_SYNC.replace("postgresql+psycopg2://", "postgresql://")
    suffix = uuid.uuid4().hex[:10]
    database = "axious_v2_completion_test_pilot_" + suffix
    manager = "pilot_manager_" + suffix
    password = "synthetic-test-password-123"
    reader = None
    with closing(psycopg2.connect(url)) as admin:
        admin.autocommit = True
        params = {key: value for key, value in admin.get_dsn_parameters().items() if key in ("host", "port")}
        try:
            with admin.cursor() as cursor:
                cursor.execute(sql.SQL("CREATE ROLE {} LOGIN CREATEROLE CREATEDB PASSWORD %s").format(sql.Identifier(manager)), (password,))
                cursor.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(database), sql.Identifier(manager)))
            from sqlalchemy.engine import URL
            env = os.environ.copy()
            env["DATABASE_URL_SYNC"] = URL.create("postgresql+psycopg2", manager, password, params.get("host"), int(params.get("port", 5432)), database).render_as_string(hide_password=False)
            env["DATABASE_URL"] = env["DATABASE_URL_SYNC"].replace("postgresql+psycopg2", "postgresql+asyncpg")
            subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=env, check=True, capture_output=True)
            with psycopg2.connect(**params, dbname=database, user=manager, password=password) as owner:
                reader = bootstrap(owner, password)
                assert bootstrap(owner, password) == reader
                with owner.cursor() as cursor:
                    cursor.execute("SELECT id, nombre FROM v2_organizacion")
                    assert cursor.fetchall() == [(PILOT_ID, "SalmoTrack Piloto")]
                    cursor.execute("SELECT count(*) FROM v2_item")
                    assert cursor.fetchone()[0] == 0
                    cursor.execute("SELECT rolsuper, rolcreaterole, rolcreatedb, rolreplication, rolbypassrls FROM pg_roles WHERE rolname=%s", (reader,))
                    assert cursor.fetchone() == (False,) * 5
            verify_reader(env["DATABASE_URL_SYNC"].replace("postgresql+psycopg2://", "postgresql://"), reader, password)
            with psycopg2.connect(**params, dbname=database, user=reader, password=password) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT count(*) FROM salmotrack_bi.stock")
                    assert cursor.fetchone()[0] == 0
                    connection.rollback()
                    cursor.execute("SET default_transaction_read_only=off")
                    for query in ("SELECT * FROM public.usuario", "SELECT * FROM salmotrack_bi.principal", "DELETE FROM salmotrack_bi.stock"):
                        with pytest.raises(psycopg2.Error):
                            cursor.execute(query)
                        connection.rollback()
        finally:
            with admin.cursor() as cursor:
                cursor.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(database)))
                if reader:
                    cursor.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(reader)))
                cursor.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(manager)))
