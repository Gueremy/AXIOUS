"""Prepara salida multietapa y traslado en la base local de integración.

SALMO_QA_ORG_SLUG=salmo-e2e-local python -m scripts.seed_browser_flow_qa
El guardado se limita a axious_v2_completion_test.
"""
import asyncio
import json
import os

from sqlalchemy import select

from app.core.config import settings
from app.database import AsyncSessionLocal
from app.models.v2 import Organizacion, TipoMovimiento, Ubicacion, Zona


async def main():
    if settings.ENVIRONMENT != "test" or "axious_v2_completion_test" not in settings.DATABASE_URL:
        raise RuntimeError("Este seed sólo puede ejecutarse en la base de integración")
    slug = os.environ["SALMO_QA_ORG_SLUG"]
    async with AsyncSessionLocal() as db:
        org = (await db.execute(select(Organizacion).where(Organizacion.slug == slug))).scalar_one()
        zone = (await db.execute(select(Zona).where(Zona.id_organizacion == org.id))).scalars().first()
        if zone is None:
            raise RuntimeError("La organización QA necesita una zona")
        second = (await db.execute(select(Ubicacion).where(
            Ubicacion.id_zona == zone.id, Ubicacion.codigo == "RACK-B-01",
        ))).scalar_one_or_none()
        if second is None:
            second = Ubicacion(id_organizacion=org.id, id_zona=zone.id,
                               codigo="RACK-B-01", capacidad_maxima=1000,
                               unidad_capacidad="kg", ocupacion_actual=0, activo=True)
            db.add(second)

        types = (
            ("SALIDA_QA_ETAPAS", "Salida QA por etapas", "salida", True, False, True,
             {"etapas": [{"codigo": "revision", "roles": []},
                          {"codigo": "autorizacion", "roles": []}],
              "estado_aprobado": "aprobada", "estado_rechazado": "rechazada"}),
            ("TRASLADO_QA", "Traslado QA", "traslado", True, True, False, {}),
        )
        for code, name, effect, requires_origin, requires_dest, approval, flow in types:
            existing = (await db.execute(select(TipoMovimiento).where(
                TipoMovimiento.id_organizacion == org.id, TipoMovimiento.codigo == code,
            ))).scalar_one_or_none()
            if existing is None:
                db.add(TipoMovimiento(id_organizacion=org.id, codigo=code, nombre=name,
                                      efecto_stock=effect, requiere_origen=requires_origin,
                                      requiere_destino=requires_dest, requiere_aprobacion=approval,
                                      flujo_aprobacion=flow, activo=True))
        await db.commit()
        print(json.dumps({"organization": slug, "second_location": second.codigo,
                          "movement_types": [row[0] for row in types]}))


asyncio.run(main())
