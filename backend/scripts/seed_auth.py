"""
scripts/seed_auth.py
Crea el usuario super_admin inicial para poder probar en Swagger.

Uso:
    cd backend
    python scripts/seed_auth.py

Credenciales que crea:
    email   : admin@skretting.cl
    password: Admin2026!
    rol     : super_admin
"""
import asyncio
import sys
import os

# Asegura que Python encuentre el módulo 'app'
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.security import get_password_hash
from app.models.usuario import Usuario


async def seed():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        # Verificar si ya existe
        result = await db.execute(
            select(Usuario).where(Usuario.email == "admin@skretting.cl")
        )
        if result.scalar_one_or_none():
            print("[OK] El usuario admin@skretting.cl ya existe. No se creo duplicado.")
            return

        admin = Usuario(
            id=str(uuid.uuid4()),
            nombre="Admin Sistema",
            email="admin@skretting.cl",
            password_hash=get_password_hash("Admin2026!"),
            codigo_empleado="EMP-001",
            rol="super_admin",
            id_sede=None,
            turno=None,
            activo=True,
        )
        db.add(admin)
        await db.commit()
        print("[OK] Usuario creado exitosamente:")
        print("   email   : admin@skretting.cl")
        print("   password: Admin2026!")
        print("   rol     : super_admin")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
