"""Create a restricted PostgreSQL login for one organization; password is read privately."""
import argparse
import getpass
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psycopg2
from psycopg2 import sql
from app.core.config import settings


def provision(organization_id, password, connection=None):
    organization_id = str(uuid.UUID(organization_id))
    if len(password) < 16:
        raise ValueError("Utiliza al menos 16 caracteres")
    if connection is None:
        url = settings.DATABASE_URL_SYNC.replace("postgresql+psycopg2://", "postgresql://")
        with psycopg2.connect(url) as connection:
            return provision(organization_id, password, connection)
    role = "salmotrack_bi_" + organization_id.replace("-", "_")
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM v2_organizacion WHERE id=%s", (organization_id,))
        if not cursor.fetchone():
            raise ValueError("Organización no encontrada")
        cursor.execute("SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls FROM pg_roles WHERE rolname=%s", (role,))
        attributes = cursor.fetchone()
        if attributes and any(attributes):
            raise ValueError("La cuenta BI existente tiene privilegios elevados; revisión manual requerida")
        if attributes is None:
            cursor.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(role)))
        # New roles already default to unprivileged. Setting SUPERUSER,
        # REPLICATION or BYPASSRLS (even to NO) requires elevated privileges.
        cursor.execute(sql.SQL("ALTER ROLE {} WITH LOGIN NOINHERIT PASSWORD %s").format(sql.Identifier(role)), (password,))
        cursor.execute("SELECT r.rolname FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.roleid JOIN pg_roles member ON member.oid=m.member WHERE member.rolname=%s", (role,))
        for (membership,) in cursor.fetchall():
            cursor.execute(sql.SQL("REVOKE {} FROM {}").format(sql.Identifier(membership), sql.Identifier(role)))
        cursor.execute("INSERT INTO salmotrack_bi.principal(login_name,id_organizacion) VALUES(%s,%s) ON CONFLICT(login_name) DO UPDATE SET id_organizacion=EXCLUDED.id_organizacion", (role, organization_id))
        cursor.execute(sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {}").format(sql.Identifier(role)))
        cursor.execute(sql.SQL("REVOKE ALL ON salmotrack_bi.principal FROM {}").format(sql.Identifier(role)))
        cursor.execute(sql.SQL("ALTER ROLE {} SET default_transaction_read_only=on").format(sql.Identifier(role)))
        cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA salmotrack_bi TO {}").format(sql.Identifier(role)))
        for view in ("sitios", "items", "ocupacion", "stock", "movimientos", "inconsistencias"):
            cursor.execute(sql.SQL("GRANT SELECT ON salmotrack_bi.{} TO {}").format(sql.Identifier(view), sql.Identifier(role)))
    return role


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("organization_id")
    args = parser.parse_args()
    password = getpass.getpass("Contraseña para la cuenta BI: ")
    if len(password) < 16:
        raise SystemExit("Utiliza al menos 16 caracteres")
    print("Cuenta BI preparada:", provision(args.organization_id, password))
