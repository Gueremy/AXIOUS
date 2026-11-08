"""Opt-in initialization of the empty Render pilot; no stock or application users."""
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import psycopg2
from app.core.config import settings
from scripts.provision_bi import provision

PILOT_SLUG = "salmotrack-piloto"
PILOT_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, "https://salmotrack-v3-qq8r.onrender.com/"))


def bootstrap(connection, password):
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(738133701)")
        cursor.execute("SELECT id FROM v2_organizacion WHERE slug=%s", (PILOT_SLUG,))
        organization = cursor.fetchone()
        if organization is None:
            cursor.execute("SELECT 1 FROM v2_organizacion LIMIT 1")
            if cursor.fetchone():
                raise ValueError("El piloto requiere una base vacía o su organización ya inicializada")
            cursor.execute("INSERT INTO v2_organizacion(id,nombre,slug,configuracion,activo) VALUES(%s,%s,%s,'{}',true)",
                           (PILOT_ID, "SalmoTrack Piloto", PILOT_SLUG))
        organization_id = organization[0] if organization else PILOT_ID
    return provision(organization_id, password, connection)


def main():
    if os.environ.get("SALMOTRACK_BOOTSTRAP_PILOT_BI") != "1":
        return
    password = os.environ.get("POWER_BI_PASSWORD", "")
    if len(password) < 16:
        raise ValueError("POWER_BI_PASSWORD debe tener al menos 16 caracteres")
    url = settings.DATABASE_URL_SYNC.replace("postgresql+psycopg2://", "postgresql://")
    with psycopg2.connect(url) as connection:
        role = bootstrap(connection, password)
    print("Piloto BI preparado. Organización: SalmoTrack Piloto; usuario:", role)


if __name__ == "__main__":
    main()
