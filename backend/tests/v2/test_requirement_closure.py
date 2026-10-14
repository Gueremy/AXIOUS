"""Regresiones de los requisitos generales del backend v2."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from decimal import Decimal
import uuid

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.core.events.event_bus import DomainEvent, EventBus
from app.modules.importacion.events import alertar_conciliacion
from app.services.v2.alerta_event_handlers import alertar_movimiento_fuera_horario
from app.services.v2.export_service import ExportServiceV2
from app.models.v2.movimiento import MovimientoV2
from tests.conftest import TestSessionLocal
from app.models.usuario import Usuario
from app.models.v2 import (
    EsquemaAtributos, Item, Organizacion, ReglaUbicacion, SaldoStock,
    Sitio, TipoMovimiento, Ubicacion, UsuarioSitio, Zona,
)


@pytest.fixture
async def contexto(db):
    suffix = uuid.uuid4().hex[:8]
    org = Organizacion(id=str(uuid.uuid4()), nombre="Cierre RG", slug=f"cierre-{suffix}")
    db.add(org)
    await db.flush()
    user = Usuario(
        id=str(uuid.uuid4()), nombre="Administrador", email=f"cierre-{suffix}@example.invalid",
        password_hash="!", codigo_empleado=f"C-{suffix}", rol="super_admin",
        id_organizacion=org.id, activo=True,
    )
    db.add(user)
    sitios = [Sitio(id=str(uuid.uuid4()), id_organizacion=org.id, codigo=f"S{i}",
                    nombre=f"Sitio {i}", tipo="bodega") for i in (1, 2)]
    db.add_all(sitios)
    await db.flush()
    zonas = [Zona(id=str(uuid.uuid4()), id_organizacion=org.id, id_sitio=s.id,
                  codigo=f"Z{i}", nombre=f"Zona {i}", tipo="sector")
             for i, s in enumerate(sitios, 1)]
    db.add_all(zonas)
    await db.flush()
    ubicaciones = [Ubicacion(
        id=str(uuid.uuid4()), id_organizacion=org.id, id_zona=z.id,
        codigo=f"U{i}", capacidad_maxima=Decimal("2"), unidad_capacidad="t",
        ocupacion_actual=Decimal("0"), permite_mezcla_lotes=True,
    ) for i, z in enumerate(zonas, 1)]
    item = Item(id=str(uuid.uuid4()), id_organizacion=org.id, codigo="SKU1",
                nombre="Item", categoria="insumo", unidad_medida="kg", atributos={"grado": "A"})
    tipo = TipoMovimiento(id=str(uuid.uuid4()), id_organizacion=org.id, codigo="ENTRADA",
                          nombre="Entrada", efecto_stock="entrada", requiere_destino=True,
                          requiere_aprobacion=False)
    db.add_all([*ubicaciones, item, tipo])
    await db.commit()
    token = create_access_token({"sub": user.id, "org_id": org.id})
    return {"org": org, "user": user, "sitios": sitios, "ubicaciones": ubicaciones,
            "item": item, "tipo": tipo, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.mark.asyncio
async def test_patch_atributos_valida_esquema(client, db, contexto):
    db.add(EsquemaAtributos(id_organizacion=contexto["org"].id, entidad="item",
                            nombre="item", version=1, activo=True,
                            schema_json={"type": "object", "properties": {"grado": {"type": "string"}},
                                         "required": ["grado"]}))
    await db.commit()
    resp = await client.patch(f"/api/v2/items/{contexto['item'].id}",
                              headers=contexto["headers"], json={"atributos": {"grado": 12}})
    assert resp.status_code == 422
    await db.refresh(contexto["item"])
    assert contexto["item"].atributos == {"grado": "A"}


@pytest.mark.asyncio
async def test_regla_de_sitio_no_bloquea_otro_sitio(client, db, contexto):
    db.add(ReglaUbicacion(id_organizacion=contexto["org"].id,
                          id_sitio=contexto["sitios"][0].id, codigo="SOLO_OTRO",
                          nombre="Solo otra categoría", tipo_regla="categorias_permitidas",
                          configuracion={"categorias": ["otro"]}, activo=True))
    await db.commit()
    base = {"id_tipo_movimiento": contexto["tipo"].id, "id_item": contexto["item"].id,
            "cantidad": 500, "unidad_medida": "kg"}
    h = contexto["headers"]
    ajeno = await client.post("/api/v2/movimientos/solicitudes", headers=h,
                              json={**base, "id_ubicacion_destino": contexto["ubicaciones"][1].id})
    assert ajeno.status_code == 201, ajeno.text
    bloqueado = await client.post("/api/v2/movimientos/solicitudes", headers=h,
                                  json={**base, "id_ubicacion_destino": contexto["ubicaciones"][0].id})
    assert bloqueado.status_code == 400
    await db.refresh(contexto["ubicaciones"][1])
    assert contexto["ubicaciones"][1].ocupacion_actual == Decimal("0.5")


@pytest.mark.asyncio
async def test_configuracion_colores_importacion_api_y_exportacion(client, db, contexto):
    h = contexto["headers"]
    otra = Organizacion(id=str(uuid.uuid4()), nombre="Otra", slug=f"otra-{uuid.uuid4().hex[:8]}")
    db.add(otra)
    await db.flush()
    db.add(Item(id_organizacion=otra.id, codigo="SOLO-OTRA", nombre="Privado",
                categoria="otro", unidad_medida="kg"))
    await db.commit()
    config = await client.patch("/api/v2/configuracion-operativa", headers=h,
                                json={"umbrales_color": {"alerta": 20, "critica": 40},
                                      "paleta_colores": {"alerta": "#123456"}})
    assert config.status_code == 200, config.text
    assert config.json()["paleta_colores"]["alerta"] == "#123456"
    entrada = await client.post("/api/v2/movimientos/solicitudes", headers=h,
                                json={"id_tipo_movimiento": contexto["tipo"].id,
                                      "id_item": contexto["item"].id,
                                      "id_ubicacion_destino": contexto["ubicaciones"][0].id,
                                      "cantidad": 500, "unidad_medida": "kg"})
    assert entrada.status_code == 201, entrada.text
    ocupacion = await client.get("/api/v2/dashboard/ocupacion", headers=h)
    assert next(x for x in ocupacion.json() if x["codigo"] == "U1")["estado"] == "alerta"
    importacion = await client.post("/api/v2/importacion/conciliar-api", headers=h,
                                    json={"fuente": "erp", "filas": [{"codigo_ubicacion": "U1",
                                                                          "codigo_item": "SKU1", "cantidad": 100}]})
    assert importacion.status_code == 200, importacion.text
    assert importacion.json()["job"]["tipo_fuente"] == "api"
    perfil = await client.post("/api/v2/importacion/mapeos", headers=h, json={
        "nombre": "ERP JSON", "mapeo": {"codigo_ubicacion": "POS", "codigo_item": "SKU",
                                         "cantidad": "QTY"},
    })
    assert perfil.status_code == 201, perfil.text
    importacion_mapeada = await client.post("/api/v2/importacion/conciliar-api", headers=h,
                                            json={"fuente": "erp", "id_mapping_profile": perfil.json()["id"],
                                                  "filas": [{"POS": "U1", "SKU": "SKU1", "QTY": 1}]})
    assert importacion_mapeada.status_code == 200, importacion_mapeada.text
    assert importacion_mapeada.json()["job"]["registros_inconsistentes"] == 0
    exportacion = await client.get("/api/v2/exportaciones/ubicaciones/csv", headers=h)
    assert exportacion.status_code == 200
    assert b"U1" in exportacion.content
    assert exportacion.headers["x-export-total"] == "2"
    items_csv = await client.get("/api/v2/exportaciones/items/csv", headers=h)
    assert items_csv.status_code == 200
    assert b"SOLO-OTRA" not in items_csv.content
    kpis_pdf = await client.get("/api/v2/exportaciones/kpis/pdf", headers=h)
    assert kpis_pdf.status_code == 200, kpis_pdf.text[:300]
    assert kpis_pdf.content.startswith(b"%PDF")
    bi_excel = await client.get("/api/v2/exportaciones/bi-stock/excel", headers=h)
    assert bi_excel.status_code == 200, bi_excel.text[:300]
    assert bi_excel.content.startswith(b"PK")


@pytest.mark.asyncio
async def test_flujo_de_dos_etapas_y_demo_retail(client, db, contexto):
    h = contexto["headers"]
    nuevo = await client.post("/api/v2/movimientos/tipos", headers=h, json={
        "codigo": "EMBARQUE", "nombre": "Embarque", "efecto_stock": "entrada",
        "requiere_destino": True, "requiere_aprobacion": True,
        "flujo_aprobacion": {"etapas": [
            {"codigo": "revision", "roles": ["jefe_bodega"]},
            {"codigo": "autorizacion", "roles": ["super_admin"]},
        ], "estado_aprobado": "confirmada", "estado_rechazado": "denegada"},
    })
    assert nuevo.status_code == 201, nuevo.text
    solicitud = await client.post("/api/v2/movimientos/solicitudes", headers=h, json={
        "id_tipo_movimiento": nuevo.json()["id"], "id_item": contexto["item"].id,
        "id_ubicacion_destino": contexto["ubicaciones"][0].id,
        "cantidad": 100, "unidad_medida": "kg",
    })
    assert solicitud.status_code == 201 and solicitud.json()["estado"] == "revision"
    sid = solicitud.json()["id"]
    jefe = Usuario(
        id=str(uuid.uuid4()), nombre="Jefe", email=f"jefe-{uuid.uuid4().hex[:8]}@example.invalid",
        password_hash="!", codigo_empleado=f"J-{uuid.uuid4().hex[:8]}",
        rol="jefe_bodega", id_organizacion=contexto["org"].id, activo=True,
    )
    db.add(jefe)
    db.add(UsuarioSitio(id_usuario=jefe.id, id_sitio=contexto["sitios"][0].id))
    await db.commit()
    jefe_token = create_access_token({"sub": jefe.id, "org_id": contexto["org"].id})
    h_jefe = {"Authorization": f"Bearer {jefe_token}"}
    etapa = await client.patch(f"/api/v2/movimientos/solicitudes/{sid}/aprobar", headers=h_jefe)
    assert etapa.status_code == 200 and etapa.json()["estado"] == "autorizacion"
    sin_rol = await client.patch(f"/api/v2/movimientos/solicitudes/{sid}/aprobar", headers=h_jefe)
    assert sin_rol.status_code == 403
    final = await client.patch(f"/api/v2/movimientos/solicitudes/{sid}/aprobar", headers=h)
    assert final.status_code == 200 and final.json()["id_solicitud"] == sid
    demo = await client.post("/api/v2/demo/seed?preset=retail&en_organizacion_actual=false", headers=h)
    assert demo.status_code == 201 and demo.json()["preset"] == "retail"


@pytest.mark.asyncio
async def test_alerta_inactividad_y_conciliacion_por_evento(client, db, contexto, monkeypatch):
    saldo = SaldoStock(
        id_organizacion=contexto["org"].id, id_ubicacion=contexto["ubicaciones"][0].id,
        id_item=contexto["item"].id, cantidad=Decimal("20"), unidad_medida="kg",
        fecha_actualizacion=datetime.now(timezone.utc) - timedelta(days=40),
    )
    db.add(saldo)
    await db.commit()
    h = contexto["headers"]
    alertas = await client.post("/api/v2/alertas/evaluar", headers=h)
    assert alertas.status_code == 200, alertas.text
    assert any(a["tipo"] == "sin_movimiento_30_dias" for a in alertas.json()["alertas_creadas"])
    retenida = await client.patch(f"/api/v2/ubicaciones/{contexto['ubicaciones'][0].id}",
                                  headers=h, json={"estado": "retenido"})
    assert retenida.status_code == 200
    reevaluacion = await client.post("/api/v2/alertas/evaluar", headers=h)
    assert any(a["tipo"] == "cuarentena_activa" for a in reevaluacion.json()["alertas_creadas"])

    import app.modules.importacion.events as events
    monkeypatch.setattr(events, "AsyncSessionLocal", TestSessionLocal)
    suscriptores_previos = {nombre: list(handlers) for nombre, handlers in EventBus._subscribers.items()}
    EventBus.subscribe("importacion.finalizada", alertar_conciliacion)
    try:
        importacion = await client.post("/api/v2/importacion/conciliar-api", headers=h,
                                        json={"fuente": "erp", "filas": [{"codigo_ubicacion": "U1",
                                                                              "codigo_item": "SKU1", "cantidad": 3000}]})
        assert importacion.status_code == 200, importacion.text
        assert importacion.json()["job"]["registros_inconsistentes"] >= 1
        activas = await client.get("/api/v2/alertas/activas", headers=h)
        assert activas.status_code == 200
        assert any(a["tipo"] == "discrepancia_inventario" for a in activas.json())
        jefe = Usuario(id=str(uuid.uuid4()), nombre="Jefe", email=f"sitio-{uuid.uuid4().hex[:8]}@example.invalid",
                       password_hash="!", codigo_empleado=f"S-{uuid.uuid4().hex[:8]}",
                       rol="jefe_bodega", id_organizacion=contexto["org"].id, activo=True)
        db.add(jefe)
        db.add(UsuarioSitio(id_usuario=jefe.id, id_sitio=contexto["sitios"][0].id))
        await db.commit()
        token_jefe = create_access_token({"sub": jefe.id, "org_id": contexto["org"].id})
        alertas_sitio = await client.get("/api/v2/alertas/activas",
                                         headers={"Authorization": f"Bearer {token_jefe}"})
        assert any(a["tipo"] == "discrepancia_inventario" for a in alertas_sitio.json())
    finally:
        EventBus._subscribers = suscriptores_previos


@pytest.mark.asyncio
async def test_unidad_personalizada_y_limite_de_regla(client, db, contexto):
    h = contexto["headers"]
    config = await client.patch("/api/v2/configuracion-operativa", headers=h,
                                json={"unidades": {"caja": {"dimension": "masa", "factor": "20"}}})
    assert config.status_code == 200
    cambio_item = await client.patch(f"/api/v2/items/{contexto['item'].id}", headers=h,
                                     json={"unidad_medida": "caja"})
    assert cambio_item.status_code == 200
    entrada = await client.post("/api/v2/movimientos/solicitudes", headers=h, json={
        "id_tipo_movimiento": contexto["tipo"].id, "id_item": contexto["item"].id,
        "id_ubicacion_destino": contexto["ubicaciones"][0].id,
        "cantidad": 10, "unidad_medida": "caja",
    })
    assert entrada.status_code == 201, entrada.text
    cambio_ubi = await client.patch(f"/api/v2/ubicaciones/{contexto['ubicaciones'][0].id}",
                                    headers=h, json={"unidad_capacidad": "kg"})
    assert cambio_ubi.status_code == 200, cambio_ubi.text
    assert Decimal(cambio_ubi.json()["ocupacion_actual"]) == Decimal("200")
    assert Decimal(cambio_ubi.json()["capacidad_maxima"]) == Decimal("2000")
    cambio_invalido = await client.patch(f"/api/v2/items/{contexto['item'].id}", headers=h,
                                        json={"unidad_medida": "kg"})
    assert cambio_invalido.status_code == 409
    regla = await client.post("/api/v2/reglas/", headers=h, json={
        "codigo": "MAX-250", "nombre": "Máximo operativo", "tipo_regla": "capacidad",
        "id_ubicacion": contexto["ubicaciones"][0].id,
        "configuracion": {"maximo": 250},
    })
    assert regla.status_code == 201, regla.text
    excede = await client.post("/api/v2/movimientos/solicitudes", headers=h, json={
        "id_tipo_movimiento": contexto["tipo"].id, "id_item": contexto["item"].id,
        "id_ubicacion_destino": contexto["ubicaciones"][0].id,
        "cantidad": 3, "unidad_medida": "caja",
    })
    assert excede.status_code == 400
    assert "MAX-250" in excede.json()["detail"]
    importacion = await client.post("/api/v2/importacion/conciliar-api", headers=h,
                                    json={"fuente": "erp", "filas": [{"codigo_ubicacion": "U1",
                                                                          "codigo_item": "SKU1", "cantidad": 100}]})
    assert importacion.status_code == 200, importacion.text
    assert importacion.json()["job"]["registros_inconsistentes"] >= 2
    assert importacion.json()["job"]["registros_validos"] == 0


@pytest.mark.asyncio
async def test_alerta_movimiento_fuera_horario(client, db, contexto, monkeypatch):
    h = contexto["headers"]
    reglas = await client.get("/api/v2/alertas/reglas", headers=h)
    regla = next(r for r in reglas.json() if r["codigo"] == "movimiento_fuera_horario")
    entrada = await client.post("/api/v2/movimientos/solicitudes", headers=h, json={
        "id_tipo_movimiento": contexto["tipo"].id, "id_item": contexto["item"].id,
        "id_ubicacion_destino": contexto["ubicaciones"][0].id,
        "cantidad": 10, "unidad_medida": "kg",
    })
    assert entrada.status_code == 201
    movimiento = (await db.execute(select(MovimientoV2).where(
        MovimientoV2.id_solicitud == entrada.json()["id"],
    ))).scalar_one()
    fecha = movimiento.fecha_hora
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=timezone.utc)
    hora = fecha.astimezone(ZoneInfo("America/Santiago")).hour
    configuracion = {"hora_inicio": (hora + 1) % 24,
                     "hora_fin": (hora + 2) % 24,
                     "zona_horaria": "America/Santiago"}
    cambiado = await client.patch(f"/api/v2/alertas/reglas/{regla['id']}", headers=h,
                                  json={"configuracion": configuracion})
    assert cambiado.status_code == 200
    import app.services.v2.alerta_event_handlers as handlers
    monkeypatch.setattr(handlers, "AsyncSessionLocal", TestSessionLocal)
    await alertar_movimiento_fuera_horario(DomainEvent(
        name="movimiento.creado", id_organizacion=contexto["org"].id,
        payload={"id_movimiento": movimiento.id},
    ))
    activas = await client.get("/api/v2/alertas/activas", headers=h)
    assert any(a["tipo"] == "movimiento_fuera_horario" for a in activas.json())


def test_exportacion_no_ejecuta_formulas_de_origen_externo():
    csv = ExportServiceV2.exportar_csv(["Código"], [["=1+1"], ["-12"]]).decode("utf-8-sig")
    assert "'=1+1" in csv
    assert "-12" in csv
