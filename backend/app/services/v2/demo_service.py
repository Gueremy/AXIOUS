"""
app/services/v2/demo_service.py
Generador de datos demo reproducibles (Fase 3B).
Presets:
- 'salmonera': Concesión acuícola, pontón, jaulas, ensilaje, alimento y peces.
- 'general': Centro de distribución logístico, racks, pallets, insumos industriales.
Incluye inconsistencias intencionales para evaluar conciliación y reglas.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.usuario import Usuario
from app.models.v2.item import Item
from app.models.v2.lote import Lote
from app.models.v2.movimiento import MovimientoV2
from app.models.v2.organizacion import Organizacion
from app.models.v2.saldo_stock import SaldoStock
from app.models.v2.sitio import Sitio
from app.models.v2.tipo_movimiento import TipoMovimiento
from app.models.v2.ubicacion import Ubicacion
from app.models.v2.zona import Zona
from app.modules.importacion.models import ImportacionJob, Inconsistencia


class DemoGeneratorService:

    @staticmethod
    async def generar_demo(
        db: AsyncSession,
        preset: str = "salmonera",
        id_organizacion_existente: str = None,
    ) -> Dict[str, Any]:
        """Genera un ecosistema completo ficticio reproducible."""
        preset = preset.lower()
        now = datetime.now(timezone.utc)

        # 1. Resolver Organización Demo
        if id_organizacion_existente:
            stmt_org = select(Organizacion).where(Organizacion.id == id_organizacion_existente)
            org = (await db.execute(stmt_org)).scalar_one()
        else:
            slug = f"demo-{preset}-{uuid.uuid4().hex[:6]}"
            nombre_org = f"Demo Acuicultura Austral ({preset.capitalize()})" if preset == "salmonera" else f"Demo Distribución Global ({preset.capitalize()})"
            org = Organizacion(
                id=str(uuid.uuid4()),
                nombre=nombre_org,
                slug=slug,
                activo=True,
                configuracion={"es_demo": True, "preset": preset},
            )
            db.add(org)
            await db.flush()

        # 2. Tipos de Movimiento
        tipo_in = TipoMovimiento(
            id=str(uuid.uuid4()),
            id_organizacion=org.id,
            codigo="RECEPCION_DEMO",
            nombre="Recepción Demo",
            efecto_stock="entrada",
            requiere_destino=True,
            requiere_aprobacion=False,
        )
        db.add(tipo_in)
        await db.flush()

        # 3. Estructura según preset
        if preset == "salmonera":
            sitio = Sitio(
                id=str(uuid.uuid4()),
                id_organizacion=org.id,
                codigo="SIT-CONC-01",
                nombre="Centro Experimental Fiordo Azul [DEMO]",
                tipo="mar",
                activo=True,
            )
            db.add(sitio)
            await db.flush()

            zona_ponton = Zona(
                id=str(uuid.uuid4()),
                id_organizacion=org.id,
                id_sitio=sitio.id,
                codigo="PONTON-01",
                nombre="Pontón Central y Bodega Seca",
                tipo="ponton",
                layout={"x": 0, "y": 0, "z": 0, "width": 30, "height": 10, "depth": 15},
            )
            zona_modulo = Zona(
                id=str(uuid.uuid4()),
                id_organizacion=org.id,
                id_sitio=sitio.id,
                codigo="MODULO-A",
                nombre="Módulo de Jaulas Sector Norte",
                tipo="modulo",
                layout={"x": 50, "y": 0, "z": 0, "width": 80, "height": 80, "depth": 25},
            )
            db.add_all([zona_ponton, zona_modulo])
            await db.flush()

            # Ubicaciones
            ubi_silo = Ubicacion(
                id=str(uuid.uuid4()),
                id_organizacion=org.id,
                id_zona=zona_ponton.id,
                codigo="SILO-ALIM-01",
                capacidad_maxima=Decimal("20000.0000"),
                unidad_capacidad="kg",
                ocupacion_actual=Decimal("12000.0000"),
                permite_mezcla_lotes=False,
                layout={"x": 5, "y": 2, "z": 0, "width": 4, "height": 4, "depth": 8},
            )
            ubi_jaula = Ubicacion(
                id=str(uuid.uuid4()),
                id_organizacion=org.id,
                id_zona=zona_modulo.id,
                codigo="JAULA-101",
                capacidad_maxima=Decimal("60000.0000"),
                unidad_capacidad="kg",
                ocupacion_actual=Decimal("45000.0000"),
                permite_mezcla_lotes=True,
                layout={"x": 10, "y": 10, "z": -15, "width": 20, "height": 20, "depth": 20},
            )
            db.add_all([ubi_silo, ubi_jaula])
            await db.flush()

            # Ítems
            item_pellet = Item(
                id=str(uuid.uuid4()),
                id_organizacion=org.id,
                codigo="ALIM-EXP-5MM",
                nombre="Pellet Nutricional 5mm [DEMO]",
                categoria="alimento",
                unidad_medida="kg",
            )
            item_pez = Item(
                id=str(uuid.uuid4()),
                id_organizacion=org.id,
                codigo="SALMON-ATL-SMOLT",
                nombre="Salmo Salar Smolt 120g [DEMO]",
                categoria="biomasa",
                unidad_medida="kg",
            )
            db.add_all([item_pellet, item_pez])
            await db.flush()

            # Lote con vencimiento
            lote_alim = Lote(
                id=str(uuid.uuid4()),
                id_organizacion=org.id,
                id_item=item_pellet.id,
                numero_lote="LOT-ALIM-2026-X",
                fecha_vencimiento=now + timedelta(days=60),
            )
            db.add(lote_alim)
            await db.flush()

            saldo_silo = SaldoStock(
                id_organizacion=org.id,
                id_ubicacion=ubi_silo.id,
                id_item=item_pellet.id,
                id_lote=lote_alim.id,
                cantidad=Decimal("12000.0000"),
                unidad_medida="kg",
            )
            db.add(saldo_silo)

        else:
            # Preset general / retail
            sitio = Sitio(
                id=str(uuid.uuid4()),
                id_organizacion=org.id,
                codigo="SIT-CD-01",
                nombre="Centro de Distribución Logístico [DEMO]",
                tipo="bodega",
                activo=True,
            )
            db.add(sitio)
            await db.flush()

            zona_rack = Zona(
                id=str(uuid.uuid4()),
                id_organizacion=org.id,
                id_sitio=sitio.id,
                codigo="PASILLO-01",
                nombre="Pasillo 01 Racks Pesados",
                tipo="pasillo",
                layout={"x": 0, "y": 0, "z": 0, "width": 50, "height": 4, "depth": 10},
            )
            db.add(zona_rack)
            await db.flush()

            ubi_pallet = Ubicacion(
                id=str(uuid.uuid4()),
                id_organizacion=org.id,
                id_zona=zona_rack.id,
                codigo="RACK-A-01",
                capacidad_maxima=Decimal("1500.0000"),
                unidad_capacidad="kg",
                ocupacion_actual=Decimal("500.0000"),
                permite_mezcla_lotes=True,
                layout={"x": 2, "y": 0, "z": 1, "width": 1.2, "height": 1.0, "depth": 1.5},
            )
            db.add(ubi_pallet)
            await db.flush()

            item_gen = Item(
                id=str(uuid.uuid4()),
                id_organizacion=org.id,
                codigo="INS-CAJA-CARTON",
                nombre="Caja Embalaje Reforzada [DEMO]",
                categoria="insumo",
                unidad_medida="kg",
            )
            db.add(item_gen)
            await db.flush()

            lote_gen = Lote(
                id=str(uuid.uuid4()),
                id_organizacion=org.id,
                id_item=item_gen.id,
                numero_lote="LOT-EMB-001",
                fecha_vencimiento=now + timedelta(days=365),
            )
            db.add(lote_gen)
            await db.flush()

            saldo_gen = SaldoStock(
                id_organizacion=org.id,
                id_ubicacion=ubi_pallet.id,
                id_item=item_gen.id,
                id_lote=lote_gen.id,
                cantidad=Decimal("500.0000"),
                unidad_medida="kg",
            )
            db.add(saldo_gen)

        await db.commit()

        return {
            "status": "success",
            "preset": preset,
            "id_organizacion": org.id,
            "organizacion_nombre": org.nombre,
            "mensaje": f"Dataset de prueba reproducido correctamente para preset '{preset}'.",
        }
