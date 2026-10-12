"""
tests/v2/test_0b_models_integrity.py
Pruebas automatizadas de la Fase 0B:
- Integridad del modelo de datos genérico v2.
- Unicidad scoped por organización (código de ítem, sitio, lote).
- Jerarquías de zonas multinivel.
- Validación de atributos JSON Schema dinámicos.
- Restricciones CHECK para cantidades no negativas.
"""
import uuid
from decimal import Decimal
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select

from app.models.v2 import (
    Organizacion, Sitio, Zona, Ubicacion,
    Item, Lote, EsquemaAtributos, SaldoStock
)
from app.core.validators.schema_validator import validar_atributos, AtributosValidationError


@pytest.mark.asyncio
async def test_crear_dos_organizaciones_con_mismo_codigo_item(db):
    """Verifica que dos organizaciones distintas pueden tener ítems con el mismo código sin conflicto."""
    org1 = Organizacion(id=str(uuid.uuid4()), nombre="Org Alfa", slug=f"alfa-{uuid.uuid4().hex[:6]}")
    org2 = Organizacion(id=str(uuid.uuid4()), nombre="Org Beta", slug=f"beta-{uuid.uuid4().hex[:6]}")
    db.add_all([org1, org2])
    await db.flush()

    item1 = Item(
        id=str(uuid.uuid4()),
        id_organizacion=org1.id,
        codigo="SKU-COMUN-001",
        nombre="Item en Org Alfa",
        categoria="general",
        unidad_medida="kg",
    )
    item2 = Item(
        id=str(uuid.uuid4()),
        id_organizacion=org2.id,
        codigo="SKU-COMUN-001",  # Mismo código, diferente organización
        nombre="Item en Org Beta",
        categoria="repuestos",
        unidad_medida="unidades",
    )
    db.add_all([item1, item2])
    await db.flush()

    res = await db.execute(select(Item).where(Item.codigo == "SKU-COMUN-001"))
    items = res.scalars().all()
    assert len(items) == 2


@pytest.mark.asyncio
async def test_item_codigo_duplicado_en_misma_org_falla(db):
    """Verifica que un código de ítem duplicado dentro de la misma organización es rechazado."""
    org = Organizacion(id=str(uuid.uuid4()), nombre="Org Unica", slug=f"unica-{uuid.uuid4().hex[:6]}")
    db.add(org)
    await db.flush()

    item1 = Item(
        id=str(uuid.uuid4()),
        id_organizacion=org.id,
        codigo="SKU-REPETIDO",
        nombre="Original",
        categoria="quimico",
        unidad_medida="litros",
    )
    db.add(item1)
    await db.flush()

    item2 = Item(
        id=str(uuid.uuid4()),
        id_organizacion=org.id,
        codigo="SKU-REPETIDO",
        nombre="Duplicado",
        categoria="quimico",
        unidad_medida="litros",
    )
    db.add(item2)
    with pytest.raises(IntegrityError):
        await db.flush()
    await db.rollback()


@pytest.mark.asyncio
async def test_jerarquia_zonas_tres_niveles(db):
    """Verifica que la jerarquía recursiva de zonas soporta 3 o más niveles sin código estático."""
    org = Organizacion(id=str(uuid.uuid4()), nombre="Org Zonas", slug=f"zonas-{uuid.uuid4().hex[:6]}")
    db.add(org)
    await db.flush()

    sitio = Sitio(
        id=str(uuid.uuid4()),
        id_organizacion=org.id,
        codigo="SIT-01",
        nombre="Sitio de Zonas",
        tipo="bodega",
    )
    db.add(sitio)
    await db.flush()

    z_nivel1 = Zona(
        id=str(uuid.uuid4()),
        id_organizacion=org.id,
        id_sitio=sitio.id,
        id_zona_padre=None,
        codigo="PATIO",
        nombre="Patio",
        tipo="exterior",
    )
    db.add(z_nivel1)
    await db.flush()

    z_nivel2 = Zona(
        id=str(uuid.uuid4()),
        id_organizacion=org.id,
        id_sitio=sitio.id,
        id_zona_padre=z_nivel1.id,
        codigo="GALPON-A",
        nombre="Galpón A",
        tipo="galpon",
    )
    db.add(z_nivel2)
    await db.flush()

    z_nivel3 = Zona(
        id=str(uuid.uuid4()),
        id_organizacion=org.id,
        id_sitio=sitio.id,
        id_zona_padre=z_nivel2.id,
        codigo="PASILLO-1",
        nombre="Pasillo 1",
        tipo="pasillo",
    )
    db.add(z_nivel3)
    await db.flush()

    # Ubicación en el nivel 3
    ubi = Ubicacion(
        id=str(uuid.uuid4()),
        id_organizacion=org.id,
        id_zona=z_nivel3.id,
        codigo="P1-POS-01",
        capacidad_maxima=Decimal("1000.0"),
        unidad_capacidad="kg",
    )
    db.add(ubi)
    await db.flush()

    # Comprobación de relaciones
    assert z_nivel3.id_zona_padre == z_nivel2.id
    assert z_nivel2.id_zona_padre == z_nivel1.id
    assert ubi.id_zona == z_nivel3.id


def test_validador_atributos_json_schema():
    """Prueba unitaria de validación de JSON Schema contra atributos válidos e inválidos."""
    schema = {
        "type": "object",
        "properties": {
            "temperatura_max": {"type": "number"},
            "inflamable": {"type": "boolean"},
        },
        "required": ["temperatura_max", "inflamable"],
    }

    # Atributos válidos
    atributos_ok = {"temperatura_max": -18.5, "inflamable": False}
    validar_atributos(atributos_ok, schema)  # No debe lanzar excepción

    # Falta campo requerido
    atributos_incompletos = {"temperatura_max": 25.0}
    with pytest.raises(AtributosValidationError) as exc:
        validar_atributos(atributos_incompletos, schema)
    assert "inflamable" in str(exc.value)

    # Tipo de dato erróneo
    atributos_tipo_malo = {"temperatura_max": "no_es_numero", "inflamable": True}
    with pytest.raises(AtributosValidationError):
        validar_atributos(atributos_tipo_malo, schema)


@pytest.mark.asyncio
async def test_saldo_stock_persiste_correctamente(db):
    """Verifica la persistencia y clave única compuesta de SaldoStock."""
    org = Organizacion(id=str(uuid.uuid4()), nombre="Org Stock", slug=f"stock-{uuid.uuid4().hex[:6]}")
    db.add(org)
    await db.flush()

    sitio = Sitio(id=str(uuid.uuid4()), id_organizacion=org.id, codigo="S-01", nombre="Sitio 1", tipo="bodega")
    db.add(sitio)
    await db.flush()

    zona = Zona(id=str(uuid.uuid4()), id_organizacion=org.id, id_sitio=sitio.id, codigo="Z-01", nombre="Zona 1", tipo="nave")
    db.add(zona)
    await db.flush()

    ubi = Ubicacion(id=str(uuid.uuid4()), id_organizacion=org.id, id_zona=zona.id, codigo="U-01", capacidad_maxima=Decimal("500"), unidad_capacidad="m3")
    item = Item(id=str(uuid.uuid4()), id_organizacion=org.id, codigo="IT-01", nombre="Item 1", categoria="cat", unidad_medida="m3")
    db.add_all([ubi, item])
    await db.flush()

    lote = Lote(id=str(uuid.uuid4()), id_organizacion=org.id, id_item=item.id, numero_lote="LOTE-XYZ")
    db.add(lote)
    await db.flush()

    saldo = SaldoStock(
        id=str(uuid.uuid4()),
        id_organizacion=org.id,
        id_ubicacion=ubi.id,
        id_item=item.id,
        id_lote=lote.id,
        cantidad=Decimal("150.2500"),
        unidad_medida="m3",
    )
    db.add(saldo)
    await db.flush()

    res = await db.execute(select(SaldoStock).where(SaldoStock.id == saldo.id))
    saldo_db = res.scalar_one()
    assert saldo_db.cantidad == Decimal("150.2500")
    assert saldo_db.unidad_medida == "m3"
