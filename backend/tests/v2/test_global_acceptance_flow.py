"""
tests/v2/test_global_acceptance_flow.py
Prueba de Criterio Global de Aceptación (Sección 28 del Plan de Implementación):
Ejecuta el flujo completo de 21 pasos end-to-end que demuestra que SalmoTrack v2
está 100% listo para que el frontend v2 se conecte:

1. Crear Organización A
2. Crear Organización B
3. Crear usuario A
4. Crear usuario B
5. Crear sitio de A
6. Crear zonas jerárquicas
7. Crear ubicaciones con capacidades/reglas
8. Crear items y lotes
9. Registrar movimientos
10. Validar capacidad/reglas
11. Aprobar según flujo configurado
12. Reintentar un movimiento offline -> no duplicarlo (idempotencia)
13. Importar CSV/Excel externo
14. Mapear columnas
15. Conciliar
16. Detectar:
    - sobrecapacidad
    - lote mezclado no permitido
    - ubicación inexistente
17. Mostrar KPIs de supervisor vía API
18. Exportar resultados (CSV, Excel, PDF)
19. Verificar que usuario B NO puede leer ningún dato de A
20. Activar pack salmonero en A -> aparecen validaciones regulatorias
21. Mantener pack apagado en B -> el núcleo funciona sin SAG/SERNAPESCA
"""
from decimal import Decimal
import uuid
import pytest
from httpx import AsyncClient

from app.core.security import create_access_token
from app.models.usuario import Usuario
from app.models.v2 import (
    Organizacion, Sitio, Zona, Ubicacion,
    Item, Lote, SaldoStock, TipoMovimiento, ModuloOrganizacion
)


@pytest.mark.asyncio
async def test_global_acceptance_21_steps_journey(client: AsyncClient, db):
    # ─── Paso 1 y 2: Crear Organizaciones A y B ───────────────────────────────
    org_a = Organizacion(id=str(uuid.uuid4()), nombre="Empresa Logística Alfa", slug=f"alfa-{uuid.uuid4().hex[:4]}")
    org_b = Organizacion(id=str(uuid.uuid4()), nombre="Empresa Logística Beta", slug=f"beta-{uuid.uuid4().hex[:4]}")
    db.add_all([org_a, org_b])
    await db.flush()

    # ─── Paso 3 y 4: Crear usuarios A y B ─────────────────────────────────────
    user_a = Usuario(
        id=str(uuid.uuid4()),
        nombre="Admin Alfa",
        email=f"admin_alfa_{uuid.uuid4().hex[:4]}@alfa.cl",
        password_hash="secret_a",
        codigo_empleado=f"EMP-ALFA-{uuid.uuid4().hex[:6]}",
        rol="super_admin",
        id_organizacion=org_a.id,
        activo=True,
    )
    user_b = Usuario(
        id=str(uuid.uuid4()),
        nombre="Admin Beta",
        email=f"admin_beta_{uuid.uuid4().hex[:4]}@beta.cl",
        password_hash="secret_b",
        codigo_empleado=f"EMP-BETA-{uuid.uuid4().hex[:6]}",
        rol="super_admin",
        id_organizacion=org_b.id,
        activo=True,
    )
    db.add_all([user_a, user_b])
    await db.flush()

    token_a = create_access_token({"sub": user_a.id, "org_id": org_a.id})
    token_b = create_access_token({"sub": user_b.id, "org_id": org_b.id})
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # ─── Paso 5: Crear sitio de A ─────────────────────────────────────────────
    resp_sitio = await client.post(
        "/api/v2/sitios/",
        headers=headers_a,
        json={"codigo": "SIT-ALFA-01", "nombre": "Bodega Principal Alfa", "tipo": "bodega"},
    )
    assert resp_sitio.status_code == 201
    sitio_a_id = resp_sitio.json()["id"]

    # ─── Paso 6: Crear zonas jerárquicas ──────────────────────────────────────
    resp_zona_padre = await client.post(
        "/api/v2/zonas/",
        headers=headers_a,
        json={"id_sitio": sitio_a_id, "codigo": "ZON-PADRE", "nombre": "Galpón 1", "tipo": "galpon"},
    )
    assert resp_zona_padre.status_code == 201
    zona_padre_id = resp_zona_padre.json()["id"]

    resp_subzona = await client.post(
        "/api/v2/zonas/",
        headers=headers_a,
        json={"id_sitio": sitio_a_id, "id_zona_padre": zona_padre_id, "codigo": "ZON-HIJA", "nombre": "Sector A1", "tipo": "sector"},
    )
    assert resp_subzona.status_code == 201
    subzona_id = resp_subzona.json()["id"]

    # ─── Paso 7: Crear ubicaciones con capacidades y reglas ───────────────────
    # Ubicación 1: Capacidad 100 kg, no permite mezcla de lotes
    resp_ubi1 = await client.post(
        "/api/v2/ubicaciones/",
        headers=headers_a,
        json={
            "id_zona": subzona_id,
            "codigo": "UBI-A1",
            "capacidad_maxima": 100.0,
            "unidad_capacidad": "kg",
            "permite_mezcla_lotes": False,
        },
    )
    assert resp_ubi1.status_code == 201
    ubi1_id = resp_ubi1.json()["id"]

    # ─── Paso 8: Crear items y lotes ──────────────────────────────────────────
    resp_item = await client.post(
        "/api/v2/items/",
        headers=headers_a,
        json={"codigo": "SKU-SALMON-01", "nombre": "Filete Premium", "categoria": "pescado", "unidad_medida": "kg"},
    )
    assert resp_item.status_code == 201
    item_id = resp_item.json()["id"]

    resp_lote1 = await client.post(
        "/api/v2/lotes/",
        headers=headers_a,
        json={"id_item": item_id, "numero_lote": "LOTE-ALFA-01"},
    )
    assert resp_lote1.status_code == 201
    lote1_id = resp_lote1.json()["id"]

    # Tipo de movimiento
    resp_tipo = await client.post(
        "/api/v2/movimientos/tipos",
        headers=headers_a,
        json={
            "codigo": "ING_DIRECTO",
            "nombre": "Ingreso Directo",
            "efecto_stock": "entrada",
            "requiere_destino": True,
            "requiere_aprobacion": False,
        },
    )
    assert resp_tipo.status_code == 201
    tipo_id = resp_tipo.json()["id"]

    # ─── Paso 9 y 10: Registrar movimientos y validar capacidad ───────────────
    # Movimiento válido de 40 kg en UBI-A1
    resp_mov1 = await client.post(
        "/api/v2/movimientos/solicitudes",
        headers=headers_a,
        json={
            "id_tipo_movimiento": tipo_id,
            "id_item": item_id,
            "id_lote": lote1_id,
            "id_ubicacion_destino": ubi1_id,
            "cantidad": 40.0,
            "unidad_medida": "kg",
        },
    )
    assert resp_mov1.status_code == 201

    # Movimiento que excede capacidad (70 kg más en UBI-A1 que ya tiene 40 de 100) -> rechazo 400
    resp_mov_over = await client.post(
        "/api/v2/movimientos/solicitudes",
        headers=headers_a,
        json={
            "id_tipo_movimiento": tipo_id,
            "id_item": item_id,
            "id_lote": lote1_id,
            "id_ubicacion_destino": ubi1_id,
            "cantidad": 70.0,
            "unidad_medida": "kg",
        },
    )
    assert resp_mov_over.status_code == 400
    assert "capacidad" in resp_mov_over.json()["detail"].lower()

    # ─── Paso 11: Aprobar según flujo configurado ─────────────────────────────
    # Crear tipo que exige aprobación
    resp_tipo_apr = await client.post(
        "/api/v2/movimientos/tipos",
        headers=headers_a,
        json={
            "codigo": "ING_CON_APROBACION",
            "nombre": "Ingreso con Aprobación",
            "efecto_stock": "entrada",
            "requiere_destino": True,
            "requiere_aprobacion": True,
        },
    )
    tipo_apr_id = resp_tipo_apr.json()["id"]

    resp_sol_pend = await client.post(
        "/api/v2/movimientos/solicitudes",
        headers=headers_a,
        json={
            "id_tipo_movimiento": tipo_apr_id,
            "id_item": item_id,
            "id_lote": lote1_id,
            "id_ubicacion_destino": ubi1_id,
            "cantidad": 10.0,
            "unidad_medida": "kg",
        },
    )
    sol_id = resp_sol_pend.json()["id"]
    assert resp_sol_pend.json()["estado"] == "pendiente"

    # Aprobar
    resp_apr = await client.patch(f"/api/v2/movimientos/solicitudes/{sol_id}/aprobar", headers=headers_a)
    assert resp_apr.status_code == 200

    # ─── Paso 12: Reintentar movimiento offline -> no duplicarlo ──────────────
    uuid_offline = str(uuid.uuid4())
    sync_batch = {
        "movimientos": [
            {
                "uuid_local": uuid_offline,
                "id_tipo_movimiento": tipo_id,
                "id_item": item_id,
                "id_lote": lote1_id,
                "id_ubicacion_destino": ubi1_id,
                "cantidad": 15.0,
                "unidad_medida": "kg",
            }
        ]
    }
    # 1. Envío inicial
    resp_sync1 = await client.post("/api/v2/movimientos/sync", headers=headers_a, json=sync_batch)
    assert resp_sync1.status_code == 200
    assert resp_sync1.json()["resultados"][0]["estado"] == "sincronizado"

    # 2. Reintento idéntico
    resp_sync2 = await client.post("/api/v2/movimientos/sync", headers=headers_a, json=sync_batch)
    assert resp_sync2.status_code == 200
    assert resp_sync2.json()["resultados"][0]["estado"] == "duplicado"

    # ─── Paso 13, 14, 15, 16: Importar, Mapear, Conciliar e Inconsistencias ───
    # Subir CSV externo que provoca sobrecapacidad, mezcla de lotes y ubicación inexistente
    csv_externo = (
        "POSICION,SKU,LOTE,CANTIDAD\n"
        "UBI-A1,SKU-SALMON-01,LOTE-ALFA-01,10.0\n"        # Válido
        "UBI-A1,SKU-SALMON-01,LOTE-ALFA-01,200.0\n"       # Sobrecapacidad
        "UBI-A1,SKU-SALMON-01,LOTE-DISTINTO,5.0\n"        # Mezcla de lotes no permitida
        "UBI-NO-EXISTE,SKU-SALMON-01,LOTE-ALFA-01,10.0\n" # Ubicación inexistente
    )
    files = {"file": ("erp_export.csv", csv_externo.encode("utf-8"), "text/csv")}
    resp_concil = await client.post("/api/v2/importacion/conciliar", headers=headers_a, files=files)
    assert resp_concil.status_code == 200
    concil_data = resp_concil.json()
    assert concil_data["job"]["registros_inconsistentes"] == 3

    tipos_inc = {i["tipo_inconsistencia"] for i in concil_data["inconsistencias"]}
    assert "sobrecapacidad" in tipos_inc
    assert "mezcla_lotes_no_permitida" in tipos_inc
    assert "ubicacion_inexistente" in tipos_inc

    # ─── Paso 17: Mostrar KPIs de supervisor vía API ──────────────────────────
    resp_kpis = await client.get("/api/v2/dashboard/kpis", headers=headers_a)
    assert resp_kpis.status_code == 200
    kpis = resp_kpis.json()
    assert float(kpis["capacidad_instalada"]) == 100.0
    assert float(kpis["stock_total"]) == 65.0  # 40 + 10 + 15
    assert kpis["cantidad_inconsistencias"] == 3

    # ─── Paso 18: Exportar resultados ─────────────────────────────────────────
    resp_csv = await client.get("/api/v2/dashboard/exportar/movimientos/csv", headers=headers_a)
    assert resp_csv.status_code == 200
    resp_xls = await client.get("/api/v2/dashboard/exportar/movimientos/excel", headers=headers_a)
    assert resp_xls.status_code == 200
    resp_pdf = await client.get("/api/v2/dashboard/exportar/movimientos/pdf", headers=headers_a)
    assert resp_pdf.status_code == 200

    # ─── Paso 19: Verificar aislamiento estricto de Usuario B ─────────────────
    # B no puede ver los sitios de A
    resp_b_sitios = await client.get("/api/v2/sitios/", headers=headers_b)
    assert len(resp_b_sitios.json()["items"]) == 0
    # B no puede consultar por ID el sitio de A
    resp_b_hack = await client.get(f"/api/v2/sitios/{sitio_a_id}", headers=headers_b)
    assert resp_b_hack.status_code == 404
    # B ve sus propios KPIs en cero
    resp_b_kpis = await client.get("/api/v2/dashboard/kpis", headers=headers_b)
    assert float(resp_b_kpis.json()["stock_total"]) == 0.0

    # ─── Paso 20: Activar pack salmonero en A -> aparecen validaciones ────────
    await client.patch("/api/v2/modulos/pack_salmonero", headers=headers_a, json={"habilitado": True})

    # Movimiento en A sin campos SAG/SERNAPESCA es rechazado
    resp_salm_fail = await client.post(
        "/api/v2/movimientos/solicitudes",
        headers=headers_a,
        json={
            "id_tipo_movimiento": tipo_id,
            "id_item": item_id,
            "id_ubicacion_destino": ubi1_id,
            "cantidad": 1.0,
            "unidad_medida": "kg",
            "atributos": {},
        },
    )
    assert resp_salm_fail.status_code == 400
    assert "sernapesca" in resp_salm_fail.json()["detail"].lower()

    # ─── Paso 21: Mantener pack apagado en B -> núcleo opera sin SAG/SERNAPESCA
    # B crea sus propios recursos y movimientos genéricos sin campos salmoneros
    resp_b_sitio = await client.post(
        "/api/v2/sitios/",
        headers=headers_b,
        json={"codigo": "SIT-BETA-01", "nombre": "Bodega Beta", "tipo": "bodega"},
    )
    sitio_b_id = resp_b_sitio.json()["id"]

    resp_b_zona = await client.post(
        "/api/v2/zonas/",
        headers=headers_b,
        json={"id_sitio": sitio_b_id, "codigo": "ZON-B", "nombre": "Zona B", "tipo": "sector"},
    )
    zona_b_id = resp_b_zona.json()["id"]

    resp_b_ubi = await client.post(
        "/api/v2/ubicaciones/",
        headers=headers_b,
        json={"id_zona": zona_b_id, "codigo": "UBI-B1", "capacidad_maxima": 500.0, "unidad_capacidad": "kg"},
    )
    ubi_b_id = resp_b_ubi.json()["id"]

    resp_b_item = await client.post(
        "/api/v2/items/",
        headers=headers_b,
        json={"codigo": "ITEM-GENERAL", "nombre": "Tornillos de Acero", "categoria": "ferreteria", "unidad_medida": "kg"},
    )
    item_b_id = resp_b_item.json()["id"]

    resp_b_tipo = await client.post(
        "/api/v2/movimientos/tipos",
        headers=headers_b,
        json={"codigo": "ING_B", "nombre": "Ingreso", "efecto_stock": "entrada", "requiere_destino": True},
    )
    tipo_b_id = resp_b_tipo.json()["id"]

    # B registra movimiento sin campos salmoneros: debe funcionar exitosamente
    resp_b_mov = await client.post(
        "/api/v2/movimientos/solicitudes",
        headers=headers_b,
        json={
            "id_tipo_movimiento": tipo_b_id,
            "id_item": item_b_id,
            "id_ubicacion_destino": ubi_b_id,
            "cantidad": 20.0,
            "unidad_medida": "kg",
            "atributos": {},
        },
    )
    assert resp_b_mov.status_code == 201
