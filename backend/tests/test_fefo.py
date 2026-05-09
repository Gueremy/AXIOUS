"""
tests/test_fefo.py  — Sprint 2
Verifica: sugerir_container_fefo ordena ASC por fecha_vencimiento.
"""
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Sede, Galpon, Container, Producto, Usuario, Movimiento
from app.services.fefo import sugerir_container_fefo
from tests.conftest import pwd_context


pytestmark = pytest.mark.asyncio


async def _setup_fefo(db: AsyncSession):
    """Crea sede, galpon, 3 containers con el mismo producto pero distintas fechas."""
    sede = Sede(id=str(uuid.uuid4()), nombre="Sede FEFO", tipo="planta", estado="activo")
    db.add(sede)
    await db.flush()

    galpon = Galpon(
        id=str(uuid.uuid4()), id_sede=sede.id,
        nombre="Galpon FEFO", codigo="FEFO", filas=3, columnas=3, estado="activo",
    )
    db.add(galpon)
    await db.flush()

    prod = Producto(
        id=str(uuid.uuid4()), nombre="Alimento FEFO",
        categoria="alimento", unidad_medida="kg", activo=True,
    )
    db.add(prod)
    await db.flush()

    usuario = Usuario(
        id=str(uuid.uuid4()), nombre="Op FEFO",
        email="opfefo@test.cl",
        password_hash=pwd_context.hash("Test1234!"),
        codigo_empleado="FEFO001", rol="operario",
        id_sede=sede.id, activo=True,
    )
    db.add(usuario)
    await db.flush()

    now = datetime.utcnow()
    containers_creados = []
    # Fechas de vencimiento en orden INVERSO al de creacion (para verificar que FEFO ordena)
    vencimientos = [
        now + timedelta(days=90),   # c1 — vence mas tarde
        now + timedelta(days=30),   # c2 — vence antes
        now + timedelta(days=60),   # c3 — intermedio
    ]
    for i, venc in enumerate(vencimientos):
        c = Container(
            id=str(uuid.uuid4()), id_galpon=galpon.id,
            codigo=f"FEFO-{i+1}", posicion_fila=1, posicion_col=i+1,
            capacidad_max=Decimal("500.00"), unidad_medida="kg",
            ocupacion_actual=Decimal("200.00"), estado="disponible",
            tipo_producto_permitido="alimento",
        )
        db.add(c)
        await db.flush()

        m = Movimiento(
            id=str(uuid.uuid4()),
            id_container=c.id,
            id_producto=prod.id,
            id_usuario=usuario.id,
            tipo="entrada_proveedor",
            estado="aprobado",
            cantidad=Decimal("200.00"),
            numero_lote=f"LOT-FEFO-{i+1}",
            fecha_vencimiento=venc,
            fecha_fabricacion=now - timedelta(days=10),
            nombre_proveedor="BioMar",
            num_guia_despacho=f"GD-{i+1}",
            registro_sanitario=f"RS-{i+1}",
            temperatura_almacen=Decimal("-2.0"),
            origen="online",
        )
        db.add(m)
        containers_creados.append(c)

    await db.flush()
    return sede, prod, containers_creados, vencimientos


class TestFEFO:
    async def test_retorna_lista(self, db: AsyncSession):
        sede, prod, containers, _ = await _setup_fefo(db)
        result = await sugerir_container_fefo(db, prod.id, sede.id)
        assert isinstance(result, list)
        assert len(result) > 0

    async def test_ordenado_por_vencimiento_asc(self, db: AsyncSession):
        """El primer resultado debe ser el que vence MAS PRONTO."""
        sede, prod, containers, vencimientos = await _setup_fefo(db)
        result = await sugerir_container_fefo(db, prod.id, sede.id)
        assert len(result) >= 2
        fechas = [r["fecha_vencimiento"] for r in result]
        assert fechas == sorted(fechas), "FEFO no ordena ASC por fecha_vencimiento"

    async def test_solo_disponibles(self, db: AsyncSession):
        """No debe sugerir containers en mantenimiento o cuarentena."""
        sede, prod, containers, _ = await _setup_fefo(db)
        # Poner el primero en mantenimiento
        containers[0].estado = "mantenimiento"
        await db.flush()
        result = await sugerir_container_fefo(db, prod.id, sede.id)
        ids_resultado = {str(r["id"]) for r in result}
        assert str(containers[0].id) not in ids_resultado

    async def test_solo_movimientos_aprobados(self, db: AsyncSession):
        """Movimientos pendientes no deben aparecer en FEFO."""
        sede = Sede(id=str(uuid.uuid4()), nombre="Sede FEFO2", tipo="planta", estado="activo")
        db.add(sede)
        galpon = Galpon(id=str(uuid.uuid4()), id_sede=sede.id, nombre="G", codigo="GG2", filas=2, columnas=2, estado="activo")
        db.add(galpon)
        prod = Producto(id=str(uuid.uuid4()), nombre="P", categoria="alimento", unidad_medida="kg", activo=True)
        db.add(prod)
        usuario = Usuario(
            id=str(uuid.uuid4()), nombre="U", email="u2@fefo.cl",
            password_hash=pwd_context.hash("x"), codigo_empleado="FF002",
            rol="operario", id_sede=sede.id, activo=True,
        )
        db.add(usuario)
        await db.flush()

        c = Container(id=str(uuid.uuid4()), id_galpon=galpon.id, codigo="C1",
                      posicion_fila=1, posicion_col=1, capacidad_max=Decimal("100.00"),
                      unidad_medida="kg", ocupacion_actual=Decimal("50.00"),
                      estado="disponible", tipo_producto_permitido="alimento")
        db.add(c)
        await db.flush()

        from datetime import datetime, timedelta
        m = Movimiento(
            id=str(uuid.uuid4()), id_container=c.id, id_producto=prod.id,
            id_usuario=usuario.id, tipo="entrada_proveedor", estado="pendiente",
            cantidad=Decimal("50.00"), numero_lote="LOT-PEND",
            fecha_vencimiento=datetime.utcnow() + timedelta(days=30),
            fecha_fabricacion=datetime.utcnow() - timedelta(days=5),
            nombre_proveedor="Prov", num_guia_despacho="GD", registro_sanitario="RS",
            temperatura_almacen=Decimal("0"), origen="online",
        )
        db.add(m)
        await db.flush()

        result = await sugerir_container_fefo(db, prod.id, sede.id)
        assert len(result) == 0, "Movimientos pendientes no deberian aparecer en FEFO"

    async def test_aislamiento_sede(self, db: AsyncSession):
        """No retorna containers de otra sede."""
        sede_a, prod_a, _, _ = await _setup_fefo(db)
        sede_b = Sede(id=str(uuid.uuid4()), nombre="Otra Sede", tipo="bodega", estado="activo")
        db.add(sede_b)
        await db.flush()
        # Buscar con sede_b pero el producto esta en sede_a
        result = await sugerir_container_fefo(db, prod_a.id, sede_b.id)
        assert len(result) == 0, "Aislamiento de sede fallido en FEFO"

    async def test_limite_respetado(self, db: AsyncSession):
        sede, prod, _, _ = await _setup_fefo(db)
        result = await sugerir_container_fefo(db, prod.id, sede.id, limite=1)
        assert len(result) <= 1
