"""
backend/scripts/demo_generator.py
Script CLI para generar organizaciones y datasets demo reproducibles (Fase 3B).
Uso:
    python scripts/demo_generator.py --preset salmonera
    python scripts/demo_generator.py --preset general
    python scripts/demo_generator.py --preset retail
    python scripts/demo_generator.py --preset portuario
"""
import argparse
import asyncio
import sys
import os

# Asegurar que 'backend' esté en el PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import AsyncSessionLocal
from app.modules.demo.service import DemoGeneratorService


async def main():
    parser = argparse.ArgumentParser(description="Generador de datasets demo para SalmoTrack v2")
    parser.add_argument(
        "--preset",
        choices=["salmonera", "general", "retail", "portuario"],
        default="salmonera",
        help="Preset de industria a generar",
    )
    args = parser.parse_args()

    print(f"🌱 Sembrando dataset demo con preset: '{args.preset}'...")
    async with AsyncSessionLocal() as session:
        resultado = await DemoGeneratorService.generar_demo(session, preset=args.preset)
        print(f"✅ Éxito: {resultado['mensaje']}")
        print(f"   Organización creada: {resultado['organizacion_nombre']} ({resultado['id_organizacion']})")


if __name__ == "__main__":
    asyncio.run(main())
