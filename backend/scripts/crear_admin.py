import asyncio
import uuid
import sys
import os

# Agregamos el directorio raíz al path para importar modulos
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.usuario import Usuario
from app.core.security import get_password_hash

async def main():
    async with AsyncSessionLocal() as db:
        # Verificar si ya existe
        result = await db.execute(select(Usuario).where(Usuario.email == "super@skretting.cl"))
        if result.scalar_one_or_none():
            print("El usuario super@skretting.cl ya existe. Contraseña: admin123")
            return
            
        admin = Usuario(
            nombre="Super Administrador Test",
            email="super@skretting.cl",
            password_hash=get_password_hash("admin123"),
            codigo_empleado="EMP-002",
            rol="super_admin",
            activo=True
        )
        db.add(admin)
        await db.commit()
        print("✅ Super Administrador creado exitosamente!")
        print("   Email: super@skretting.cl")
        print("   Clave: admin123")

if __name__ == "__main__":
    asyncio.run(main())
