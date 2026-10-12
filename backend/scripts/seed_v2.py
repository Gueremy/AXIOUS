"""
scripts/seed_v2.py
Poblamiento de datos de demostración reproducibles para SalmoTrack v2.
Crea 2 organizaciones independientes con sitios, jerarquías de zonas, ubicaciones,
ítems con diferentes categorías y unidades, lotes, saldos y esquemas de atributos JSON Schema.
"""
import asyncio
import uuid
from decimal import Decimal
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from app.database import AsyncSessionLocal
from app.models.v2 import (
    Organizacion,
    Sitio,
    Zona,
    Ubicacion,
    Item,
    Lote,
    EsquemaAtributos,
    SaldoStock,
)


async def seed_v2_data():
    async with AsyncSessionLocal() as db:
        # Verificar si ya existen organizaciones
        existing = await db.execute(select(Organizacion).where(Organizacion.slug.in_(["austral", "central"])))
        if existing.scalars().all():
            print("Organizaciones v2 ya existen en la base de datos.")
            return

        print("Poblando datos demo SalmoTrack v2...")

        # ─── ORGANIZACIÓN A: Logística Austral ──────────────────────────────
        org_a = Organizacion(
            id=str(uuid.uuid4()),
            nombre="Logística Austral S.A.",
            slug="austral",
            activo=True,
            configuracion={"industria": "agroindustrial", "moneda": "CLP", "permite_reentregas": True},
        )
        db.add(org_a)

        # Esquema de atributos para items en Org A
        esquema_item_a = EsquemaAtributos(
            id=str(uuid.uuid4()),
            id_organizacion=org_a.id,
            entidad="item",
            nombre="atributos_materia_prima",
            version=1,
            schema_json={
                "type": "object",
                "properties": {
                    "humedad_pct": {"type": "number", "minimum": 0, "maximum": 100},
                    "temperatura_max_c": {"type": "number"},
                    "origen": {"type": "string"},
                },
                "required": ["origen"],
            },
            activo=True,
        )
        db.add(esquema_item_a)

        # Sitio A
        sitio_a = Sitio(
            id=str(uuid.uuid4()),
            id_organizacion=org_a.id,
            codigo="SIT-PMO-01",
            nombre="Centro Logístico Puerto Montt",
            tipo="planta_procesamiento",
            descripcion="Planta principal de almacenamiento en tierra",
            ubicacion_geografica="Ruta 5 Sur Km 1024, Puerto Montt",
            atributos={"certificacion": "ISO-9001", "superficie_m2": 5000},
            activo=True,
        )
        db.add(sitio_a)

        # Jerarquía de Zonas en Sitio A: Patio Principal -> Bodega Seca -> Pasillo 01
        zona_a_nivel1 = Zona(
            id=str(uuid.uuid4()),
            id_organizacion=org_a.id,
            id_sitio=sitio_a.id,
            id_zona_padre=None,
            codigo="PATIO-A",
            nombre="Patio Principal de Maniobras",
            tipo="patio",
            layout={"x": 0, "y": 0, "ancho": 100, "largo": 100},
            atributos={"superficie": "asfalto"},
            activo=True,
        )
        db.add(zona_a_nivel1)

        zona_a_nivel2 = Zona(
            id=str(uuid.uuid4()),
            id_organizacion=org_a.id,
            id_sitio=sitio_a.id,
            id_zona_padre=zona_a_nivel1.id,
            codigo="BOD-SECA",
            nombre="Bodega de Carga Seca",
            tipo="bodega",
            layout={"x": 10, "y": 10, "ancho": 40, "largo": 40},
            atributos={"control_temperatura": False},
            activo=True,
        )
        db.add(zona_a_nivel2)

        zona_a_nivel3 = Zona(
            id=str(uuid.uuid4()),
            id_organizacion=org_a.id,
            id_sitio=sitio_a.id,
            id_zona_padre=zona_a_nivel2.id,
            codigo="PAS-01",
            nombre="Pasillo de Estanterías 01",
            tipo="pasillo",
            layout={"fila_inicio": 1, "fila_fin": 10},
            atributos={"ancho_metros": 3.5},
            activo=True,
        )
        db.add(zona_a_nivel3)

        # Ubicación A1
        ubi_a1 = Ubicacion(
            id=str(uuid.uuid4()),
            id_organizacion=org_a.id,
            id_zona=zona_a_nivel3.id,
            codigo="P01-RACK-01",
            capacidad_maxima=Decimal("5000.0000"),
            unidad_capacidad="kg",
            ocupacion_actual=Decimal("1200.0000"),
            permite_mezcla_lotes=False,
            estado="disponible",
            layout={"pos_x": 1, "pos_y": 1, "pos_z": 1},
            atributos={"refrigerado": False},
            activo=True,
        )
        db.add(ubi_a1)

        # Items y Lotes Org A
        item_a1 = Item(
            id=str(uuid.uuid4()),
            id_organizacion=org_a.id,
            codigo="MP-HAR-001",
            nombre="Harina de Pescado Concentrada 68%",
            categoria="materia_prima",
            unidad_medida="kg",
            atributos={"origen": "Calbuco", "humedad_pct": 8.5},
            activo=True,
        )
        db.add(item_a1)

        ahora = datetime.now(timezone.utc)
        lote_a1 = Lote(
            id=str(uuid.uuid4()),
            id_organizacion=org_a.id,
            id_item=item_a1.id,
            numero_lote="LOT-AUS-2026-01",
            fecha_fabricacion=ahora - timedelta(days=20),
            fecha_vencimiento=ahora + timedelta(days=160),
            atributos={"analisis_lab": "APROBADO", "laboratorio": "BioControl"},
            estado="activo",
        )
        db.add(lote_a1)

        # Saldo en stock Org A
        saldo_a1 = SaldoStock(
            id=str(uuid.uuid4()),
            id_organizacion=org_a.id,
            id_ubicacion=ubi_a1.id,
            id_item=item_a1.id,
            id_lote=lote_a1.id,
            cantidad=Decimal("1200.0000"),
            unidad_medida="kg",
        )
        db.add(saldo_a1)

        # ─── ORGANIZACIÓN B: Distribuidora Central ─────────────────────────
        org_b = Organizacion(
            id=str(uuid.uuid4()),
            nombre="Distribuidora Central SpA",
            slug="central",
            activo=True,
            configuracion={"industria": "retail_logistics", "moneda": "CLP"},
        )
        db.add(org_b)

        sitio_b = Sitio(
            id=str(uuid.uuid4()),
            id_organizacion=org_b.id,
            codigo="SIT-STGO-HUB",
            nombre="Hub Metropolitano Pudahuel",
            tipo="cross_dock",
            descripcion="Centro de transferencia logística",
            ubicacion_geografica="Enea Pudahuel, Región Metropolitana",
            atributos={"docks_carga": 12},
            activo=True,
        )
        db.add(sitio_b)

        zona_b1 = Zona(
            id=str(uuid.uuid4()),
            id_organizacion=org_b.id,
            id_sitio=sitio_b.id,
            id_zona_padre=None,
            codigo="NAVE-DIST",
            nombre="Nave de Distribución Rápida",
            tipo="nave",
            layout={"superficie_m2": 3200},
            atributos={"altura_metros": 12},
            activo=True,
        )
        db.add(zona_b1)

        ubi_b1 = Ubicacion(
            id=str(uuid.uuid4()),
            id_organizacion=org_b.id,
            id_zona=zona_b1.id,
            codigo="DIST-POS-01",
            capacidad_maxima=Decimal("200.0000"),
            unidad_capacidad="pallets",
            ocupacion_actual=Decimal("45.0000"),
            permite_mezcla_lotes=True,
            estado="disponible",
            layout={"pos_x": 5, "pos_y": 10},
            atributos={"tipo_estanteria": "drive_in"},
            activo=True,
        )
        db.add(ubi_b1)

        item_b1 = Item(
            id=str(uuid.uuid4()),
            id_organizacion=org_b.id,
            codigo="EMB-CAJA-50",
            nombre="Cajas de Cartón Corrugado 50x50x40",
            categoria="empaque_embalaje",
            unidad_medida="unidades",
            atributos={"resistencia_bct_kg": 450},
            activo=True,
        )
        db.add(item_b1)

        lote_b1 = Lote(
            id=str(uuid.uuid4()),
            id_organizacion=org_b.id,
            id_item=item_b1.id,
            numero_lote="LOT-EMB-883",
            fecha_fabricacion=ahora - timedelta(days=5),
            fecha_vencimiento=None,  # No vence
            atributos={"proveedor": "Cartones Chile"},
            estado="activo",
        )
        db.add(lote_b1)

        saldo_b1 = SaldoStock(
            id=str(uuid.uuid4()),
            id_organizacion=org_b.id,
            id_ubicacion=ubi_b1.id,
            id_item=item_b1.id,
            id_lote=lote_b1.id,
            cantidad=Decimal("45.0000"),
            unidad_medida="pallets",
        )
        db.add(saldo_b1)

        await db.commit()
        print("Seed SalmoTrack v2 completado con éxito (2 organizaciones creadas).")


if __name__ == "__main__":
    asyncio.run(seed_v2_data())
