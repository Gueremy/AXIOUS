"""
tests/v2/test_1e_import_reconciliation.py
Pruebas del módulo de importación y conciliación ERP/WMS (Fase 1E):
- Creación, guardado y reutilización de perfiles de mapeo de columnas.
- Conciliación de archivos CSV con detección de:
    * Sobrecapacidad.
    * Mezcla de lotes no permitida.
    * Ubicaciones inexistentes.
- Conciliación de archivos Excel (.xlsx).
- Registro inmutable de Jobs e Inconsistencias con auditoría.
- Aislamiento multi-tenant estricto.
"""
from decimal import Decimal
import io
import uuid
import pytest
from httpx import AsyncClient
import openpyxl

from app.core.security import create_access_token
from app.models.usuario import Usuario
from app.models.v2 import (
    Organizacion, Sitio, Zona, Ubicacion,
    Item, Lote, SaldoStock, ReglaUbicacion
)
from app.modules.importacion.models import ImportacionJob, Inconsistencia, MappingProfile


@pytest.fixture
async def setup_conciliacion_fixture(db):
    """Configura Organización A y B con ubicaciones con restricciones para pruebas de conciliación."""
    # Org A
    org_a = Organizacion(id=str(uuid.uuid4()), nombre="Logística Conciliación A", slug=f"concil-a-{uuid.uuid4().hex[:4]}")
    db.add(org_a)
    await db.flush()

    user_a = Usuario(
        id=str(uuid.uuid4()),
        nombre="Operario Conciliación A",
        email=f"concil_a_{uuid.uuid4().hex[:4]}@concil.cl",
        password_hash="fake",
        codigo_empleado=f"EMP-CNC-A-{uuid.uuid4().hex[:6]}",
        rol="super_admin",
        id_organizacion=org_a.id,
        activo=True,
    )
    db.add(user_a)
    await db.flush()

    sitio_a = Sitio(id=str(uuid.uuid4()), id_organizacion=org_a.id, codigo="SIT-CNC-01", nombre="Bodega Central ERP", tipo="bodega")
    db.add(sitio_a)
    await db.flush()

    zona_a = Zona(id=str(uuid.uuid4()), id_organizacion=org_a.id, id_sitio=sitio_a.id, codigo="ZON-A", nombre="Sector A", tipo="sector")
    db.add(zona_a)
    await db.flush()

    # 1. Ubicación Normal con capacidad holgada (5000 kg)
    ubi_normal = Ubicacion(
        id=str(uuid.uuid4()),
        id_organizacion=org_a.id,
        id_zona=zona_a.id,
        codigo="POS-OK-01",
        capacidad_maxima=Decimal("5000.0000"),
        unidad_capacidad="kg",
        ocupacion_actual=Decimal("100.0000"),
        permite_mezcla_lotes=True,
    )

    # 2. Ubicación con casi tope de capacidad (Capacidad 100 kg, ocupación 90 kg -> 20 kg externos causará sobrecapacidad)
    ubi_llena = Ubicacion(
        id=str(uuid.uuid4()),
        id_organizacion=org_a.id,
        id_zona=zona_a.id,
        codigo="POS-CAP-02",
        capacidad_maxima=Decimal("100.0000"),
        unidad_capacidad="kg",
        ocupacion_actual=Decimal("90.0000"),
        permite_mezcla_lotes=True,
    )

    # 3. Ubicación que NO permite mezcla de lotes y ya tiene stock de LOTE-ORIGINAL
    ubi_sin_mezcla = Ubicacion(
        id=str(uuid.uuid4()),
        id_organizacion=org_a.id,
        id_zona=zona_a.id,
        codigo="POS-NOMIX-03",
        capacidad_maxima=Decimal("1000.0000"),
        unidad_capacidad="kg",
        ocupacion_actual=Decimal("200.0000"),
        permite_mezcla_lotes=False,
    )
    db.add_all([ubi_normal, ubi_llena, ubi_sin_mezcla])
    await db.flush()

    # Ítems y Lotes
    item_alimento = Item(
        id=str(uuid.uuid4()),
        id_organizacion=org_a.id,
        codigo="SKU-ALIMENTO-01",
        nombre="Alimento Concentrado Premium",
        categoria="alimento",
        unidad_medida="kg",
    )
    db.add(item_alimento)
    await db.flush()

    lote_existente = Lote(
        id=str(uuid.uuid4()),
        id_organizacion=org_a.id,
        id_item=item_alimento.id,
        numero_lote="LOTE-ORIGINAL",
    )
    db.add(lote_existente)
    await db.flush()

    # Saldo de LOTE-ORIGINAL en ubi_sin_mezcla
    saldo_nomix = SaldoStock(
        id_organizacion=org_a.id,
        id_ubicacion=ubi_sin_mezcla.id,
        id_item=item_alimento.id,
        id_lote=lote_existente.id,
        cantidad=Decimal("200.0000"),
        unidad_medida="kg",
    )
    db.add(saldo_nomix)
    await db.flush()

    token_a = create_access_token({"sub": user_a.id, "org_id": org_a.id})

    # Org B
    org_b = Organizacion(id=str(uuid.uuid4()), nombre="Logística Conciliación B", slug=f"concil-b-{uuid.uuid4().hex[:4]}")
    db.add(org_b)
    await db.flush()

    user_b = Usuario(
        id=str(uuid.uuid4()),
        nombre="Admin B",
        email=f"concil_b_{uuid.uuid4().hex[:4]}@concil.cl",
        password_hash="fake",
        codigo_empleado=f"EMP-CNC-B-{uuid.uuid4().hex[:6]}",
        rol="super_admin",
        id_organizacion=org_b.id,
        activo=True,
    )
    db.add(user_b)
    await db.flush()

    token_b = create_access_token({"sub": user_b.id, "org_id": org_b.id})

    await db.commit()

    return {
        "org_a": org_a,
        "token_a": token_a,
        "ubi_normal": ubi_normal,
        "ubi_llena": ubi_llena,
        "ubi_sin_mezcla": ubi_sin_mezcla,
        "item_alimento": item_alimento,
        "lote_existente": lote_existente,
        "org_b": org_b,
        "token_b": token_b,
    }


@pytest.mark.asyncio
async def test_mapping_profile_lifecycle(client: AsyncClient, setup_conciliacion_fixture):
    """Verifica guardar y reutilizar un perfil de mapeo configurable."""
    ctx = setup_conciliacion_fixture
    headers = {"Authorization": f"Bearer {ctx['token_a']}"}

    payload = {
        "nombre": "SAP WMS Export Standard",
        "descripcion": "Mapeo para exports nocturnos de SAP",
        "mapeo": {
            "codigo_ubicacion": "LGORT_BIN",
            "codigo_item": "MATNR",
            "numero_lote": "CHARG",
            "cantidad": "MENGE",
        },
    }

    # 1. Crear perfil
    resp = await client.post("/api/v2/importacion/mapeos", json=payload, headers=headers)
    assert resp.status_code == 201
    perfil = resp.json()
    assert perfil["nombre"] == "SAP WMS Export Standard"
    assert perfil["mapeo"]["codigo_item"] == "MATNR"

    # 2. Listar perfiles
    resp_list = await client.get("/api/v2/importacion/mapeos", headers=headers)
    assert resp_list.status_code == 200
    assert any(p["id"] == perfil["id"] for p in resp_list.json())


@pytest.mark.asyncio
async def test_conciliacion_csv_detecta_inconsistencias(client: AsyncClient, setup_conciliacion_fixture):
    """
    Sube un CSV con 4 filas externas:
    - Fila 1: Válida (entra en POS-OK-01).
    - Fila 2: Sobrecapacidad (POS-CAP-02 tiene 90/100, suma 30).
    - Fila 3: Mezcla de lote no permitida (POS-NOMIX-03 contiene LOTE-ORIGINAL, se intenta LOTE-NUEVO).
    - Fila 4: Ubicación inexistente (POS-FANTASMA).
    """
    ctx = setup_conciliacion_fixture
    headers = {"Authorization": f"Bearer {ctx['token_a']}"}

    csv_content = (
        "POSICION,SKU,LOTE,CANTIDAD\n"
        "POS-OK-01,SKU-ALIMENTO-01,LOT-VAL-1,50.0\n"
        "POS-CAP-02,SKU-ALIMENTO-01,LOT-SOBRECAP,30.0\n"
        "POS-NOMIX-03,SKU-ALIMENTO-01,LOTE-NUEVO,25.0\n"
        "POS-FANTASMA,SKU-ALIMENTO-01,LOT-GHOST,10.0\n"
    )

    files = {"file": ("sap_inventory.csv", csv_content.encode("utf-8"), "text/csv")}
    resp = await client.post("/api/v2/importacion/conciliar", files=files, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    job = data["job"]
    assert job["total_registros"] == 4
    assert job["registros_validos"] == 1
    assert job["registros_inconsistentes"] == 3

    inconsistencias = data["inconsistencias"]
    tipos = {inc["tipo_inconsistencia"] for inc in inconsistencias}
    assert "sobrecapacidad" in tipos
    assert "mezcla_lotes_no_permitida" in tipos
    assert "ubicacion_inexistente" in tipos

    # Consultar detalle del job por endpoint GET
    resp_job = await client.get(f"/api/v2/importacion/jobs/{job['id']}/inconsistencias", headers=headers)
    assert resp_job.status_code == 200
    assert len(resp_job.json()) == 3


@pytest.mark.asyncio
async def test_codigo_ubicacion_duplicado_se_resuelve_con_zona(client: AsyncClient, db, setup_conciliacion_fixture):
    ctx = setup_conciliacion_fixture
    original = ctx["ubi_normal"]
    zone = Zona(id=str(uuid.uuid4()), id_organizacion=ctx["org_a"].id,
                id_sitio=(await db.get(Zona, original.id_zona)).id_sitio,
                codigo="ZON-B", nombre="Sector B", tipo="sector")
    db.add(zone)
    await db.flush()
    db.add(Ubicacion(id=str(uuid.uuid4()), id_organizacion=ctx["org_a"].id,
                     id_zona=zone.id, codigo=original.codigo,
                     capacidad_maxima=5000, unidad_capacidad="kg"))
    await db.commit()
    headers = {"Authorization": f"Bearer {ctx['token_a']}"}
    csv_content = ("SITIO,ZONA,POSICION,SKU,CANTIDAD\n"
                   f"SIT-CNC-01,,{original.codigo},SKU-ALIMENTO-01,10\n"
                   f"SIT-CNC-01,ZON-A,{original.codigo},SKU-ALIMENTO-01,10\n")
    response = await client.post("/api/v2/importacion/conciliar", headers=headers,
                                 files={"file": ("duplicadas.csv", csv_content.encode(), "text/csv")})
    assert response.status_code == 200, response.text
    assert response.json()["job"]["registros_validos"] == 1
    assert [i["tipo_inconsistencia"] for i in response.json()["inconsistencias"]] == ["ubicacion_ambigua"]


@pytest.mark.asyncio
async def test_conciliacion_excel_valida_y_procesa(client: AsyncClient, setup_conciliacion_fixture):
    """Genera en memoria un archivo Excel .xlsx válido y ejecuta la conciliación."""
    ctx = setup_conciliacion_fixture
    headers = {"Authorization": f"Bearer {ctx['token_a']}"}

    # Crear libro openpyxl en memoria
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["POSICION", "SKU", "LOTE", "CANTIDAD"])
    ws.append(["POS-OK-01", "SKU-ALIMENTO-01", "LOT-XLS-01", 100])
    ws.append(["POS-INEXISTENTE", "SKU-ALIMENTO-01", "LOT-XLS-02", 50])

    excel_buffer = io.BytesIO()
    wb.save(excel_buffer)
    excel_bytes = excel_buffer.getvalue()

    files = {"file": ("conteo_bodega.xlsx", excel_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    resp = await client.post("/api/v2/importacion/conciliar", files=files, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["job"]["total_registros"] == 2
    assert data["job"]["registros_validos"] == 1
    assert data["job"]["registros_inconsistentes"] == 1
    assert data["inconsistencias"][0]["tipo_inconsistencia"] == "ubicacion_inexistente"


@pytest.mark.asyncio
async def test_aislamiento_multitenant_conciliacion(client: AsyncClient, setup_conciliacion_fixture):
    """Verifica que Org B no pueda ver jobs ni inconsistencias de Org A."""
    ctx = setup_conciliacion_fixture
    headers_a = {"Authorization": f"Bearer {ctx['token_a']}"}
    headers_b = {"Authorization": f"Bearer {ctx['token_b']}"}

    csv_content = "POSICION,SKU,LOTE,CANTIDAD\nPOS-OK-01,SKU-ALIMENTO-01,LOT-1,10.0\n"
    files = {"file": ("datos_a.csv", csv_content.encode("utf-8"), "text/csv")}
    resp_a = await client.post("/api/v2/importacion/conciliar", files=files, headers=headers_a)
    job_a_id = resp_a.json()["job"]["id"]

    # Usuario de Org B intenta consultar las inconsistencias de Org A
    resp_b = await client.get(f"/api/v2/importacion/jobs/{job_a_id}/inconsistencias", headers=headers_b)
    assert resp_b.status_code == 404
