"""
tests/v2/test_1f_dashboard_and_export.py
Pruebas de KPIs de supervisor y servicios de exportación (Fase 1F):
- Cálculo real de los 5 indicadores de supervisor.
- Inconsistencias recientes con referencias a ubicación.
- Exportación multi-formato reutilizable (CSV, Excel, PDF) sin exponer RUT (Ley 19.628).
- Aislamiento estricto multi-tenant de métricas y exportaciones.
"""
from decimal import Decimal
import io
import uuid
import zipfile
import pytest
from httpx import AsyncClient
import openpyxl
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.usuario import Usuario
from app.models.v2 import (
    Organizacion, Sitio, Zona, Ubicacion,
    Item, Lote, SaldoStock, TipoMovimiento, MovimientoV2
)
from app.modules.importacion.models import ImportacionJob, Inconsistencia


@pytest.fixture
async def setup_dashboard_fixture(db):
    """Crea datos reales en Organizaciones A y B para comprobar KPIs y reportes."""
    # Org A
    org_a = Organizacion(id=str(uuid.uuid4()), nombre="Logística Dashboard A", slug=f"dash-a-{uuid.uuid4().hex[:4]}")
    db.add(org_a)
    await db.flush()

    user_a = Usuario(
        id=str(uuid.uuid4()),
        nombre="Supervisor A",
        email=f"sup_a_{uuid.uuid4().hex[:4]}@dash.cl",
        password_hash="fake",
        codigo_empleado=f"EMP-DSH-A-{uuid.uuid4().hex[:6]}",
        rol="super_admin",
        id_organizacion=org_a.id,
        activo=True,
    )
    db.add(user_a)
    await db.flush()

    sitio_a = Sitio(id=str(uuid.uuid4()), id_organizacion=org_a.id, codigo="SIT-DSH-01", nombre="Bodega Dashboard", tipo="bodega")
    db.add(sitio_a)
    await db.flush()

    zona_a = Zona(id=str(uuid.uuid4()), id_organizacion=org_a.id, id_sitio=sitio_a.id, codigo="ZON-A", nombre="Sector Central", tipo="sector")
    db.add(zona_a)
    await db.flush()

    # Ubicación 1: Capacidad 1000, ocupación 400
    ubi_a1 = Ubicacion(
        id=str(uuid.uuid4()),
        id_organizacion=org_a.id,
        id_zona=zona_a.id,
        codigo="UBI-DSH-01",
        capacidad_maxima=Decimal("1000.0000"),
        unidad_capacidad="kg",
        ocupacion_actual=Decimal("400.0000"),
    )
    # Ubicación 2: Capacidad 1000, libre (ocupación 0)
    ubi_a2 = Ubicacion(
        id=str(uuid.uuid4()),
        id_organizacion=org_a.id,
        id_zona=zona_a.id,
        codigo="UBI-DSH-02",
        capacidad_maxima=Decimal("1000.0000"),
        unidad_capacidad="kg",
        ocupacion_actual=Decimal("0.0000"),
    )
    db.add_all([ubi_a1, ubi_a2])
    await db.flush()

    item_a = Item(
        id=str(uuid.uuid4()),
        id_organizacion=org_a.id,
        codigo="SKU-DSH-01",
        nombre="Salmón Fresco Calibre 4-5",
        categoria="pescado",
        unidad_medida="kg",
    )
    db.add(item_a)
    await db.flush()

    lote_a = Lote(id=str(uuid.uuid4()), id_organizacion=org_a.id, id_item=item_a.id, numero_lote="LOT-DSH-01")
    db.add(lote_a)
    await db.flush()

    # Saldo de stock: 400 kg
    saldo_a = SaldoStock(
        id_organizacion=org_a.id,
        id_ubicacion=ubi_a1.id,
        id_item=item_a.id,
        id_lote=lote_a.id,
        cantidad=Decimal("400.0000"),
        unidad_medida="kg",
    )
    db.add(saldo_a)
    await db.flush()

    # Movimiento confirmado
    tipo_mov = TipoMovimiento(
        id=str(uuid.uuid4()),
        id_organizacion=org_a.id,
        codigo="ING_NORMAL",
        nombre="Ingreso Normal",
        efecto_stock="entrada",
        requiere_destino=True,
        requiere_aprobacion=False,
    )
    db.add(tipo_mov)
    await db.flush()

    mov = MovimientoV2(
        id=str(uuid.uuid4()),
        id_organizacion=org_a.id,
        id_tipo_movimiento=tipo_mov.id,
        id_item=item_a.id,
        id_lote=lote_a.id,
        id_ubicacion_destino=ubi_a1.id,
        id_usuario=user_a.id,
        cantidad=Decimal("400.0000"),
        unidad_medida="kg",
        efecto_stock="entrada",
        atributos={},
    )
    db.add(mov)
    await db.flush()

    # Inconsistencia registrada
    job = ImportacionJob(
        id=str(uuid.uuid4()),
        id_organizacion=org_a.id,
        id_usuario=user_a.id,
        nombre_archivo="sap_dump.csv",
        tipo_fuente="csv",
        total_registros=1,
        registros_inconsistentes=1,
        resumen={},
    )
    db.add(job)
    await db.flush()

    inc = Inconsistencia(
        id=str(uuid.uuid4()),
        id_organizacion=org_a.id,
        id_importacion_job=job.id,
        fila_origen=2,
        tipo_inconsistencia="sobrecapacidad",
        motivo="Exceso de peso sobre capacidad",
        codigo_ubicacion=ubi_a1.codigo,
        codigo_item=item_a.codigo,
        numero_lote=lote_a.numero_lote,
        cantidad_externa=Decimal("700.0000"),
        resuelto=False,
    )
    db.add(inc)
    await db.flush()

    token_a = create_access_token({"sub": user_a.id, "org_id": org_a.id})

    # Org B (vacía)
    org_b = Organizacion(id=str(uuid.uuid4()), nombre="Logística Dashboard B", slug=f"dash-b-{uuid.uuid4().hex[:4]}")
    db.add(org_b)
    await db.flush()

    user_b = Usuario(
        id=str(uuid.uuid4()),
        nombre="Supervisor B",
        email=f"sup_b_{uuid.uuid4().hex[:4]}@dash.cl",
        password_hash="fake",
        codigo_empleado=f"EMP-DSH-B-{uuid.uuid4().hex[:6]}",
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
        "ubi_a1": ubi_a1,
        "ubi_a2": ubi_a2,
        "org_b": org_b,
        "token_b": token_b,
    }


@pytest.mark.asyncio
async def test_dashboard_kpis_cinco_indicadores(client: AsyncClient, setup_dashboard_fixture):
    """Verifica que los 5 indicadores mínimos se calculen de forma exacta y aislada."""
    ctx = setup_dashboard_fixture
    headers = {"Authorization": f"Bearer {ctx['token_a']}"}

    resp = await client.get("/api/v2/dashboard/kpis", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # 1. Capacidad instalada: 1000 + 1000 = 2000 kg
    assert Decimal(str(data["capacidad_instalada"])) == Decimal("2000.0000")
    # 2. Stock total acumulado: 400 kg
    assert Decimal(str(data["stock_total"])) == Decimal("400.0000")
    # 3. Ubicaciones libres: 1 (ubi_a2 con 0 kg)
    assert data["ubicaciones_libres"] == 1
    # 4. Porcentaje de uso global: (400 / 2000) * 100 = 20.0%
    assert data["porcentaje_uso"] == 20.0
    # 5. Cantidad de inconsistencias: 1
    assert data["cantidad_inconsistencias"] == 1


@pytest.mark.asyncio
async def test_dashboard_inconsistencias_con_referencia_ubicacion(client: AsyncClient, setup_dashboard_fixture):
    """Verifica que las inconsistencias contengan la referencia a la ubicación para navegación."""
    ctx = setup_dashboard_fixture
    headers = {"Authorization": f"Bearer {ctx['token_a']}"}

    resp = await client.get("/api/v2/dashboard/inconsistencias-recientes", headers=headers)
    assert resp.status_code == 200
    inconsistencias = resp.json()
    assert len(inconsistencias) >= 1

    item = inconsistencias[0]
    assert item["codigo_ubicacion"] == "UBI-DSH-01"
    assert item["tipo_inconsistencia"] == "sobrecapacidad"


@pytest.mark.asyncio
async def test_resumen_gerencia_usa_movimientos_reales_y_aisla_tenant(client: AsyncClient, setup_dashboard_fixture):
    ctx = setup_dashboard_fixture
    headers_a = {"Authorization": f"Bearer {ctx['token_a']}"}
    headers_b = {"Authorization": f"Bearer {ctx['token_b']}"}
    response = await client.get("/api/v2/dashboard/gerencia", headers=headers_a)
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data["movimientos_diarios"]) == 15
    assert sum(day["total"] for day in data["movimientos_diarios"]) == 1
    assert data["top_items"][0]["nombre"] == "Salmón Fresco Calibre 4-5"
    assert data["top_items"][0]["movimientos"] == 1
    other = await client.get("/api/v2/dashboard/gerencia", headers=headers_b)
    assert other.status_code == 200
    assert sum(day["total"] for day in other.json()["movimientos_diarios"]) == 0
    assert other.json()["top_items"] == []


@pytest.mark.asyncio
async def test_exportacion_completa_zip_paginado_y_aislado(client: AsyncClient, db, setup_dashboard_fixture):
    ctx = setup_dashboard_fixture
    original = (await db.execute(select(MovimientoV2).where(
        MovimientoV2.id_organizacion == ctx["org_a"].id,
    ))).scalar_one()
    db.add(MovimientoV2(
        id=str(uuid.uuid4()), id_organizacion=original.id_organizacion,
        id_tipo_movimiento=original.id_tipo_movimiento, id_item=original.id_item,
        id_lote=original.id_lote, id_ubicacion_destino=original.id_ubicacion_destino,
        id_usuario=original.id_usuario, cantidad=Decimal("1"),
        unidad_medida=original.unidad_medida, efecto_stock="entrada", atributos={},
    ))
    await db.commit()

    response = await client.get(
        "/api/v2/exportaciones/movimientos/excel/completo?size=1",
        headers={"Authorization": f"Bearer {ctx['token_a']}"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["X-Export-Total"] == "2"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == {"pagina-001.xlsx", "pagina-002.xlsx", "manifest.json"}
        assert openpyxl.load_workbook(io.BytesIO(archive.read("pagina-001.xlsx"))).active.max_row == 2
        assert openpyxl.load_workbook(io.BytesIO(archive.read("pagina-002.xlsx"))).active.max_row == 2

    other = await client.get(
        "/api/v2/exportaciones/movimientos/excel/completo?size=1",
        headers={"Authorization": f"Bearer {ctx['token_b']}"},
    )
    assert other.status_code == 200
    assert other.headers["X-Export-Total"] == "0"


@pytest.mark.asyncio
async def test_exportacion_movimientos_csv_excel_pdf(client: AsyncClient, setup_dashboard_fixture):
    """Verifica la exportación en los 3 formatos (CSV, Excel, PDF) y que ninguno exponga RUT."""
    ctx = setup_dashboard_fixture
    headers = {"Authorization": f"Bearer {ctx['token_a']}"}

    # 1. CSV
    resp_csv = await client.get("/api/v2/dashboard/exportar/movimientos/csv", headers=headers)
    assert resp_csv.status_code == 200
    assert "text/csv" in resp_csv.headers["content-type"]
    csv_text = resp_csv.content.decode("utf-8-sig")
    assert "ID Movimiento" in csv_text
    assert "rut" not in csv_text.lower()

    # 2. Excel (.xlsx)
    resp_excel = await client.get("/api/v2/dashboard/exportar/movimientos/excel", headers=headers)
    assert resp_excel.status_code == 200
    assert "openxmlformats" in resp_excel.headers["content-type"]
    wb = openpyxl.load_workbook(io.BytesIO(resp_excel.content))
    assert "Movimientos" in wb.sheetnames
    ws = wb["Movimientos"]
    assert ws.cell(row=1, column=1).value == "ID Movimiento"

    # 3. PDF
    resp_pdf = await client.get("/api/v2/dashboard/exportar/movimientos/pdf", headers=headers)
    assert resp_pdf.status_code == 200
    assert "application/pdf" in resp_pdf.headers["content-type"]
    assert resp_pdf.content.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_aislamiento_multitenant_dashboard(client: AsyncClient, setup_dashboard_fixture):
    """Verifica que Org B vea sus propios contadores en 0 y no tenga acceso a los datos de Org A."""
    ctx = setup_dashboard_fixture
    headers_b = {"Authorization": f"Bearer {ctx['token_b']}"}

    resp_b = await client.get("/api/v2/dashboard/kpis", headers=headers_b)
    assert resp_b.status_code == 200
    data_b = resp_b.json()

    assert Decimal(str(data_b["capacidad_instalada"])) == Decimal("0")
    assert Decimal(str(data_b["stock_total"])) == Decimal("0")
    assert data_b["cantidad_inconsistencias"] == 0

    # Inconsistencias recientes para B deben ser vacías
    resp_inc_b = await client.get("/api/v2/dashboard/inconsistencias-recientes", headers=headers_b)
    assert resp_inc_b.status_code == 200
    assert len(resp_inc_b.json()) == 0
