"""Synthetic browser-test data. Refuses every database except the local test file."""
import asyncio
from pathlib import Path
import sys
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy.engine import make_url
from app.core.config import settings
from app.core.security import get_password_hash
from app.database import Base, engine, AsyncSessionLocal
import app.main  # Register all module tables before creating the isolated schema.
from app.models import Usuario
from app.models.v2 import Organizacion, Sitio, Zona, Ubicacion, Item, Lote, TipoMovimiento, SaldoStock, UsuarioSitio, MovimientoV2


async def seed():
    url = make_url(settings.DATABASE_URL)
    expected = (Path(__file__).resolve().parents[1] / ".cache" / "browser-test.sqlite").resolve()
    if settings.ENVIRONMENT != "test" or url.drivername != "sqlite+aiosqlite" or Path(url.database).resolve() != expected:
        raise SystemExit("Solo se permite la base local .cache/browser-test.sqlite con ENVIRONMENT=test")
    expected.parent.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    ident = lambda name: str(uuid.uuid5(uuid.NAMESPACE_URL, "salmotrack-browser-test/" + name))
    async with AsyncSessionLocal() as db:
        org = Organizacion(id=ident("org"), nombre="Empresa privada de prueba", slug="browser-test")
        db.add(org); await db.flush()
        user = Usuario(id=ident("user"), id_organizacion=org.id, nombre="Operaria privada de prueba",
            email="browser@example.cl", password_hash=get_password_hash("BrowserTest123!"), codigo_empleado="BROWSER-01", rol="operario", activo=True)
        admin = Usuario(id=ident("admin"), id_organizacion=org.id, nombre="Administración de prueba",
            email="browser-admin@example.cl", password_hash=get_password_hash("BrowserTest123!"), codigo_empleado="BROWSER-00", rol="super_admin", activo=True)
        site = Sitio(id=ident("site"), id_organizacion=org.id, codigo="S01", nombre="Bodega privada de prueba", tipo="bodega")
        item = Item(id=ident("item"), id_organizacion=org.id, codigo="SKU001", nombre="Insumo privado de prueba", categoria="general", unidad_medida="kg")
        db.add_all([user, admin, site, item]); await db.flush()
        limited = Usuario(id=ident("limited-user"), id_organizacion=org.id, nombre="Operario con acceso limitado",
            email="browser-limited@example.cl", password_hash=get_password_hash("BrowserTest123!"),
            codigo_empleado="BROWSER-02", rol="operario", activo=True)
        limited_site = Sitio(id=ident("limited-site"), id_organizacion=org.id, codigo="S02", nombre="Bodega limitada", tipo="bodega")
        db.add_all([limited, limited_site]); await db.flush()
        limited_zone = Zona(id=ident("limited-zone"), id_organizacion=org.id, id_sitio=limited_site.id,
            codigo="B02-SEC01", nombre="Sector limitado", tipo="sector")
        db.add(limited_zone); await db.flush()
        db.add(UsuarioSitio(id_usuario=limited.id, id_sitio=limited_site.id))
        db.add(Ubicacion(id=ident("limited-location"), id_organizacion=org.id, id_zona=limited_zone.id,
            codigo="P0099", capacidad_maxima=1000, unidad_capacidad="kg", ocupacion_actual=0,
            estado="disponible", layout={"posicion_fila": 0, "posicion_col": 0}))
        zone = Zona(id=ident("zone"), id_organizacion=org.id, id_sitio=site.id, codigo="B01-SEC01", nombre="Sector de prueba", tipo="sector")
        lot = Lote(id=ident("lot"), id_organizacion=org.id, id_item=item.id, numero_lote="LOTE-E2E")
        db.add_all([zone, lot]); await db.flush()
        db.add(UsuarioSitio(id_usuario=user.id, id_sitio=site.id))
        for index in (1, 2):
            db.add(Ubicacion(id=ident(f"location{index}"), id_organizacion=org.id, id_zona=zone.id,
                codigo=f"P000{index}", capacidad_maxima=1000, unidad_capacidad="kg", ocupacion_actual=100 if index == 1 else 0,
                estado="disponible", layout={"posicion_fila":0,"posicion_col":index - 1}))
        for effect in ("entrada", "salida", "traslado"):
            db.add(TipoMovimiento(id=ident(effect), id_organizacion=org.id, codigo=effect.upper(), nombre=effect.capitalize(), efecto_stock=effect,
                requiere_origen=effect in ("salida", "traslado"), requiere_destino=effect in ("entrada", "traslado"), requiere_aprobacion=False))
        await db.flush()
        db.add(SaldoStock(id_organizacion=org.id, id_ubicacion=ident("location1"), id_item=item.id, id_lote=lot.id, cantidad=100, unidad_medida="kg"))
        db.add(MovimientoV2(id_organizacion=org.id, id_tipo_movimiento=ident("entrada"), id_item=item.id, id_lote=lot.id,
            id_ubicacion_destino=ident("location1"), id_usuario=user.id, cantidad=100, unidad_medida="kg", efecto_stock="entrada"))
        await db.commit()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
