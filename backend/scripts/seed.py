"""
scripts/seed.py  — AXI-10
Poblar la BD con datos de Skretting para desarrollo y demos.

Uso:
    cd backend
    python scripts/seed.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from passlib.context import CryptContext

from app.core.config import settings
from app.models import (
    Sede, Galpon, Container, Producto,
    Usuario, Movimiento,
)
from app.database import Base

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)
engine = create_engine(settings.DATABASE_URL_SYNC, echo=False)


def limpiar_bd(session: Session):
    # TRUNCATE bypasses row-level DELETE triggers (e.g. trg_movimiento_immutable)
    session.execute(text(
        "TRUNCATE TABLE log_auditoria, alerta, movimiento, usuario_galpon, "
        "container, galpon, usuario, producto, sede, refresh_token RESTART IDENTITY CASCADE"
    ))
    session.commit()
    print("  BD limpiada")


def seed(session: Session):
    now = datetime.utcnow()

    # ── Sedes (4) ────────────────────────────────────────────────────────────
    sedes_data = [
        {"nombre": "Ponton Chiloe",      "tipo": "ponton", "ubicacion": "Canal Dalcahue, Chiloe"},
        {"nombre": "Ponton Aysen",       "tipo": "ponton", "ubicacion": "Fiordo Aysen, Aysen"},
        {"nombre": "Planta Puerto Montt","tipo": "planta", "ubicacion": "Puerto Montt, Los Lagos"},
        {"nombre": "Bodega Insumos",     "tipo": "bodega", "ubicacion": "Puerto Montt, Los Lagos"},
    ]
    sedes = []
    for d in sedes_data:
        s = Sede(id=str(uuid.uuid4()), estado="activo", **d)
        session.add(s)
        sedes.append(s)
    session.flush()
    print(f"  Sedes creadas: {len(sedes)}")

    # ── Usuarios (2 por rol = 10) ─────────────────────────────────────────────
    roles = ["super_admin", "admin_sede", "jefe_bodega", "operario", "gerencia"]
    usuarios = []
    emp_idx = 1
    for i, rol in enumerate(roles):
        sede_idx = i % len(sedes)
        for j in range(2):
            u = Usuario(
                id=str(uuid.uuid4()),
                nombre=f"{rol.replace('_', ' ').title()} {j+1}",
                email=f"{rol.replace('_','.')}{j+1}@skretting.cl",
                password_hash=pwd_context.hash("Skretting2026!"),
                codigo_empleado=f"SKR{str(emp_idx).zfill(4)}",
                rol=rol,
                id_sede=sedes[sede_idx].id,
                activo=True,
            )
            session.add(u)
            usuarios.append(u)
            emp_idx += 1
    session.flush()
    print(f"  Usuarios creados: {len(usuarios)}")

    # ── Productos (5 por categoria = 25) ──────────────────────────────────────
    categorias = ["alimento", "quimico", "veterinario", "equipo", "repuesto"]
    productos = []
    for cat in categorias:
        for i in range(5):
            p = Producto(
                id=str(uuid.uuid4()),
                nombre=f"{cat.title()} {i+1}",
                codigo_barras=f"{cat[:3].upper()}{str(i+1).zfill(5)}",
                categoria=cat,
                unidad_medida="kg" if cat in ("alimento", "quimico", "veterinario") else "unidad",
                stock_minimo=Decimal("50.00"),
                descripcion=f"Producto {cat} para Skretting",
                activo=True,
            )
            session.add(p)
            productos.append(p)
    session.flush()
    print(f"  Productos creados: {len(productos)}")

    # ── Galpones (3 por sede = 12) ────────────────────────────────────────────
    galpones = []
    for sede in sedes:
        for g in range(3):
            letra = chr(65 + g)  # A, B, C
            codigo = f"{sede.nombre[:3].upper()}{letra}"[:10]
            galpon = Galpon(
                id=str(uuid.uuid4()),
                id_sede=sede.id,
                nombre=f"Galpon {letra}",
                codigo=codigo,
                filas=5,
                columnas=6,
                estado="activo",
            )
            session.add(galpon)
            galpones.append(galpon)
    session.flush()
    print(f"  Galpones creados: {len(galpones)}")

    # ── Containers (15 por galpon = 180) ─────────────────────────────────────
    tipos = ["alimento","alimento","alimento","quimico","quimico",
             "veterinario","veterinario","equipo","repuesto","general",
             "general","general","general","general","general"]
    estados_c = ["disponible","disponible","disponible","medio","medio",
                 "medio","critico","critico","mantenimiento","cuarentena",
                 "disponible","disponible","disponible","disponible","disponible"]
    ocup_pcts = [0,0,0,0.5,0.6,0.7,0.85,0.9,0,0,0.1,0.2,0.3,0.15,0.05]

    containers = []
    for galpon in galpones:
        for c_idx in range(15):
            fila = (c_idx // 6) + 1
            col  = (c_idx % 6) + 1
            cap  = Decimal("1000.00")
            ocup = cap * Decimal(str(ocup_pcts[c_idx]))
            container = Container(
                id=str(uuid.uuid4()),
                id_galpon=galpon.id,
                codigo=f"{galpon.codigo}-{str(c_idx+1).zfill(2)}"[:15],
                posicion_fila=fila,
                posicion_col=col,
                capacidad_max=cap,
                unidad_medida="kg",
                ocupacion_actual=ocup,
                estado=estados_c[c_idx],
                tipo_producto_permitido=tipos[c_idx],
            )
            session.add(container)
            containers.append(container)
    session.flush()
    print(f"  Containers creados: {len(containers)}")

    # ── Movimientos (50 con campos SERNAPESCA) ────────────────────────────────
    jefe = next(u for u in usuarios if u.rol == "jefe_bodega")
    operario = next(u for u in usuarios if u.rol == "operario")
    alim_containers = [c for c in containers if c.tipo_producto_permitido == "alimento"]
    alim_productos  = [p for p in productos  if p.categoria == "alimento"]

    for i in range(50):
        container = alim_containers[i % len(alim_containers)]
        producto  = alim_productos[i % len(alim_productos)]
        offset    = i * 3

        m = Movimiento(
            id=str(uuid.uuid4()),
            id_container=container.id,
            id_producto=producto.id,
            id_usuario=operario.id,
            id_usuario_aprobador=jefe.id,
            tipo="entrada_proveedor",
            estado="aprobado",
            cantidad=Decimal(str(50 + (i * 7) % 200)),
            numero_lote=f"LOT-{str(i+1).zfill(4)}-SKR",
            fecha_fabricacion=now - timedelta(days=offset + 30),
            fecha_vencimiento=now + timedelta(days=180 - offset),
            nombre_proveedor="BioMar Chile S.A.",
            num_guia_despacho=f"GD-{10000+i}",
            registro_sanitario=f"RS-SKR-{2000+i}",
            temperatura_almacen=Decimal("-2.50"),
            fecha_hora=now - timedelta(days=offset),
            fecha_aprobacion=now - timedelta(days=offset),
            origen="online",
        )
        session.add(m)

    session.flush()
    print("  Movimientos creados: 50")
    session.commit()


def main():
    print("Seed Skretting Chile Ltda.")
    print("-" * 40)
    Base.metadata.create_all(bind=engine)
    with Session(engine) as session:
        limpiar_bd(session)
        seed(session)
    print("-" * 40)
    print("Seed completado.")


if __name__ == "__main__":
    main()
