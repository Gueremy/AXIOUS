import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import AsyncSessionLocal
from app.models.usuario import Usuario
from sqlalchemy import select

async def main():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Usuario))
        users = result.scalars().all()
        for u in users:
            print(f"Email: {u.email} | Rol: {u.rol} | Pass: ??? (intenta generarla o cambiarla en bd)")

asyncio.run(main())
