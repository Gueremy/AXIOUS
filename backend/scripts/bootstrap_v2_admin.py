"""Crea la primera organización y cuenta v2 desde JSON recibido por stdin.

No acepta contraseñas en argumentos ni muestra su valor en la salida.
"""
import asyncio
import json
import re
import sys
import uuid

from sqlalchemy import select

from app.core.security import get_password_hash
from app.database import AsyncSessionLocal
from app.models.usuario import Usuario
from app.models.v2.organizacion import Organizacion


async def bootstrap(payload: dict) -> str:
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))
    org_name = str(payload.get("org_name", "")).strip()
    org_slug = str(payload.get("org_slug", "")).strip().lower()
    user_name = str(payload.get("user_name", "Administrador")).strip()
    if not ("@" in email and len(email) <= 150):
        raise ValueError("Correo de administrador inválido")
    if len(password) < 12 or len(password.encode("utf-8")) > 72:
        raise ValueError("La contraseña debe tener al menos 12 caracteres y hasta 72 bytes")
    if not (1 <= len(org_name) <= 150 and 1 <= len(user_name) <= 100):
        raise ValueError("Nombre de organización o usuario inválido")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,99}", org_slug):
        raise ValueError("Código de organización inválido")

    async with AsyncSessionLocal() as db:
        async with db.begin():
            org = (await db.execute(select(Organizacion).where(Organizacion.slug == org_slug))).scalar_one_or_none()
            existing = (await db.execute(select(Usuario).where(Usuario.email == email))).scalar_one_or_none()
            if existing:
                if not org or existing.id_organizacion != org.id:
                    raise ValueError("El correo ya pertenece a otra organización")
                return "La cuenta administradora ya existe; no se cambió su contraseña"
            if org is None:
                org = Organizacion(id=str(uuid.uuid4()), nombre=org_name, slug=org_slug,
                                   activo=True, configuracion={})
                db.add(org)
                await db.flush()
            db.add(Usuario(
                id=str(uuid.uuid4()), nombre=user_name, email=email,
                password_hash=get_password_hash(password),
                codigo_empleado=f"ADM-{uuid.uuid4().hex[:12].upper()}",
                rol="super_admin", id_organizacion=org.id, activo=True,
            ))
    return "Cuenta administradora v2 creada"


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        print(asyncio.run(bootstrap(payload)))
    except (ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
