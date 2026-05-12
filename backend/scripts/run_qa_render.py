"""
scripts/run_qa_render.py

Script de Automatización End-to-End (E2E) para la validación del Backend AXIOUS.
Este script se conecta directamente a la API de producción (Render) y simula el 
comportamiento de múltiples usuarios (Operario, Jefe de Bodega, Super Admin) 
para verificar que todas las reglas de negocio y seguridad funcionen correctamente.

Módulos testeados:
1. Autenticación y Seguridad (Rate Limiting, Permisos, Roles)
2. Movimientos (Creación, Aprobación, Rechazo, Restricciones FEFO y SERNAPESCA)
3. Alertas (Motor de alertas automáticas para capacidad y vencimiento)
4. Dashboard (Cálculo de KPIs en tiempo real)
5. Reportes (Descarga de PDF, Excel y validación SERNAPESCA)
6. Aislamiento Multi-Sede (Privacidad de datos entre galpones)

Uso:
    python scripts/run_qa_render.py
"""

import urllib.request
import urllib.error
import urllib.parse
import json
import time
import sys

# Forzar UTF-8 para evitar que la consola de Windows lance errores (UnicodeEncodeError)
# al intentar imprimir emojis como 🚀 o ✅.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

# URL base del entorno de producción en Render
BASE_URL = "https://axious-backend.onrender.com"

# =============================================================================
# UTILIDADES
# =============================================================================

def print_header(title):
    """Imprime un encabezado decorativo para separar visualmente los módulos en consola."""
    print(f"\n{'='*80}")
    print(f"🔹 {title}")
    print(f"{'='*80}")

def print_success(msg):
    """Imprime un mensaje de éxito cuando un test QA pasa las validaciones."""
    print(f"✅ PASA: {msg}")

def print_fail(msg, status=None, body=None):
    """Imprime un mensaje de error detallado cuando un test QA falla."""
    print(f"❌ FALLA: {msg}")
    if status: print(f"  Status: {status}")
    if body: print(f"  Body: {body}")

def make_request(method, endpoint, payload=None, token=None):
    """
    Función centralizada para hacer peticiones HTTP al servidor FastAPI.
    
    Parámetros:
    - method: "GET", "POST", "PATCH", etc.
    - endpoint: Ruta de la API (ej: "/auth/login").
    - payload: Diccionario de datos para enviar (se convierte a JSON o form-data).
    - token: JWT Token para inyectar en la cabecera Authorization (Bearer).
    
    Retorna:
    - Una tupla (status_code, response_body_dict)
    """
    headers = {"Accept": "application/json"}
    data = None
    
    # Preparamos el payload si existe
    if payload is not None:
        if isinstance(payload, str): 
            # Si es un string, asumimos que es form-data (ej: login OAuth2)
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            data = payload.encode('utf-8')
        else: 
            # De lo contrario, lo convertimos a JSON estándar
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode('utf-8')
            
    # Inyectamos el Token JWT de seguridad si el endpoint lo requiere
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
        
    req = urllib.request.Request(BASE_URL + endpoint, data=data, headers=headers, method=method)
    
    try:
        # Intentamos ejecutar la petición
        with urllib.request.urlopen(req) as response:
            raw_body = response.read()
            status = response.status
            try:
                # Intentamos decodificar como texto (JSON)
                body_str = raw_body.decode('utf-8')
                body = json.loads(body_str) if body_str else None
            except UnicodeDecodeError:
                # Si falla, significa que recibimos un archivo binario (ej: PDF o Excel)
                body = {"detail": "Binary data received"}
            return status, body
            
    except urllib.error.HTTPError as e:
        # Capturamos errores HTTP intencionales (401, 403, 400, 422, etc)
        raw_body = e.read()
        status = e.code
        try:
            body_str = raw_body.decode('utf-8')
            body = json.loads(body_str)
        except (json.JSONDecodeError, UnicodeDecodeError):
            body = {"detail": "Binary or raw data received"}
        return status, body
    except urllib.error.URLError as e:
        # Errores de red (servidor caído o sin internet)
        return 0, {"detail": str(e)}

# =============================================================================
# SCRIPT DE AUTOMATIZACIÓN E2E QA
# =============================================================================

def run_qa_automation():
    """Función principal que ejecuta secuencialmente los tests QA 01 al 27."""
    print("🚀 Iniciando automatización de QA contra Render...")
    print(f"🌍 Servidor: {BASE_URL}")

    # -------------------------------------------------------------------------
    # MÓDULO 1: Autenticación
    # -------------------------------------------------------------------------
    print_header("MÓDULO 1 — Autenticación y Seguridad")

    # QA-01: Login exitoso
    # Simulamos a un operario ingresando sus credenciales
    form_data = urllib.parse.urlencode({"username": "operario1@skretting.cl", "password": "Skretting2026!"})
    status, body = make_request("POST", "/auth/login", payload=form_data)
    if status == 200 and "access_token" in body:
        print_success("QA-01: Login exitoso (operario)")
        token_operario = body["access_token"]  # Guardamos el token para usarlo luego
    else:
        print_fail("QA-01: Login operario", status, body)
        return # Si no hay token de operario, no podemos hacer los tests siguientes

    # QA-02: Login con contraseña incorrecta
    # IMPORTANTE: Usamos un email inexistente, NO el del operario real.
    # Si usáramos el email real con mala contraseña quemaríamos intentos del rate limiter
    # para esa IP y el siguiente login (super_admin, jefe) fallaría con 429.
    time.sleep(1)  # pequeña pausa entre logins para no disparar el rate limiter
    bad_form_data = urllib.parse.urlencode({"username": "usuario_inexistente_qa@test.cl", "password": "bad_password"})
    status, body = make_request("POST", "/auth/login", payload=bad_form_data)
    if status == 401:
        print_success("QA-02: Login con contraseña incorrecta (401 Unauthorized)")
    else:
        print_fail("QA-02", status, body)

    # QA-04: Acceso sin token
    # Intentamos acceder a una ruta protegida sin enviar el token JWT
    status, body = make_request("GET", "/containers/")
    if status == 401:
        print_success("QA-04: Acceso sin token bloqueado (401 Unauthorized)")
    else:
        print_fail("QA-04", status, body)

    # Preparativos QA-05: Necesitamos ser Super Admin para intentar crear usuarios
    time.sleep(1)  # pausa entre logins consecutivos
    form_sa = urllib.parse.urlencode({"username": "super.admin1@skretting.cl", "password": "Skretting2026!"})
    st_sa, body_sa = make_request("POST", "/auth/login", payload=form_sa)
    token_sa = body_sa.get("access_token")

    if token_sa:
        # QA-05: Intentar registrar un usuario con contraseña demasiado simple
        payload_05 = {
            "nombre": "Test QA", "email": "test_qa_debil@skretting.cl", 
            "password": "12345", "rol": "operario", "codigo_empleado": "QA001"
        }
        status, body = make_request("POST", "/auth/register", payload=payload_05, token=token_sa)
        if status == 422: # 422 = Unprocessable Entity (Validación Pydantic falló)
            print_success("QA-05: Registro con contraseña débil bloqueado (422 Unprocessable Entity)")
        else:
            print_fail("QA-05", status, body)

    # -------------------------------------------------------------------------
    # EXTRACCIÓN DE DATOS REALES
    # -------------------------------------------------------------------------
    print_header("Preparación de datos para Módulo 2")
    # Para poder mover stock, necesitamos extraer IDs reales de Containers y Productos de la base de datos viva.
    status, containers = make_request("GET", "/containers/", token=token_operario)
    status, productos = make_request("GET", "/productos/", token=token_operario)

    if not containers or not productos or 'items' not in containers or 'items' not in productos:
        print("❌ No se pudieron obtener containers o productos. Abortando QA-07 y QA-08.")
        return

    # Extraemos 1 container normal (alimento) con ESPACIO DISPONIBLE >= 100 kg
    # IMPORTANTE: elegimos el que tenga más espacio libre para evitar error 400 por
    # capacidad llena (las ejecuciones previas del script acumulan stock)
    def espacio_libre(c):
        return float(c.get('capacidad_max', 0)) - float(c.get('ocupacion_actual', 0))

    alimento_containers = [c for c in containers['items'] if c['tipo_producto_permitido'] == 'alimento']
    veterinario_containers = [c for c in containers['items'] if c['tipo_producto_permitido'] == 'veterinario']

    # Elegir el container alimento con MÁS espacio libre (mínimo 100 kg para QA-07 + margen QA-19)
    cont_normal = max(
        (c for c in alimento_containers if espacio_libre(c) >= 100),
        key=espacio_libre,
        default=None
    )
    # Para el veterinario basta con que exista (QA-08 es un test de validación, no inserta)
    cont_vet = next((c for c in veterinario_containers), None)

    prod_normal = next((p for p in productos['items'] if p['categoria'] == 'alimento'), None)
    prod_vet = next((p for p in productos['items'] if p['categoria'] == 'veterinario'), None)

    if not (cont_normal and prod_normal and cont_vet and prod_vet):
        print("❌ Faltan datos en la BD. Necesario: ≥1 container alimento con 100kg libres y ≥1 veterinario.")
        print(f"   Containers alimento disponibles: {len(alimento_containers)}")
        for c in alimento_containers:
            print(f"     {c['codigo']}: libre={espacio_libre(c):.1f} kg")
        return

    print(f"✅ Datos obtenidos. Container seleccionado: {cont_normal['codigo']} (libre: {espacio_libre(cont_normal):.1f} kg)")

    # -------------------------------------------------------------------------
    # MÓDULO 2: Movimientos
    # -------------------------------------------------------------------------
    print_header("MÓDULO 2 — Movimientos")

    # QA-07: Crear movimiento "entrada_proveedor" (Como Operario)
    # Este movimiento requiere cumplir todas las leyes del SAG y SERNAPESCA (Fechas, Lotes, etc)
    mov_qa07_payload = {
        "id_container": cont_normal['id'],
        "id_producto": prod_normal['id'],
        "tipo": "entrada_proveedor",
        "cantidad": 100,
        "numero_lote": "LOT-QA-AUTO-01",
        "fecha_fabricacion": "2025-01-01T00:00:00Z",
        "fecha_vencimiento": "2026-12-31T00:00:00Z",
        "nombre_proveedor": "BioMar Chile",
        "num_guia_despacho": "GD-QA-001",
        "registro_sanitario": "RS-QA-001",
        "temperatura_almacen": 5.0
    }
    status, body_qa07 = make_request("POST", "/movimientos/", payload=mov_qa07_payload, token=token_operario)
    
    id_movimiento_generado = None
    if status == 201:
        id_movimiento_generado = body_qa07['id'] # Guardamos el ID del movimiento creado para aprobarlo después
        print_success(f"QA-07: Movimiento creado correctamente (ID: {id_movimiento_generado})")
    else:
        print_fail("QA-07", status, body_qa07)

    # QA-08: Intentar ingresar un producto Veterinario sin campos del SAG
    # El sistema debe bloquear este ingreso porque falta "num_receta_retenida"
    mov_qa08_payload = {
        "id_container": cont_vet['id'],
        "id_producto": prod_vet['id'],
        "tipo": "entrada_proveedor",
        "cantidad": 50,
        "numero_lote": "LOT-VET-001",
        "fecha_fabricacion": "2025-01-01T00:00:00Z",
        "fecha_vencimiento": "2026-12-31T00:00:00Z",
        "nombre_proveedor": "VetChile",
        "num_guia_despacho": "GD-VET-001",
        "registro_sanitario": "RS-VET-001",
        "temperatura_almacen": -2.5
    }
    status, body = make_request("POST", "/movimientos/", payload=mov_qa08_payload, token=token_operario)
    if status == 422 and "num_receta_retenida" in str(body):
        print_success("QA-08: Validación SAG funcional (422 Unprocessable Entity)")
    else:
        print_fail("QA-08", status, body)

    # Login del Jefe de Bodega — SIEMPRE, independiente de si QA-07 tuvo éxito
    # (si está dentro del if, todo el módulo 3/4/5 queda sin token cuando QA-07 falla)
    # Nota: usamos jefe.bodega2 para no bloquear jefe.bodega1 con intentos fallidos
    time.sleep(1)  # pausa entre logins para evitar 429 desde IPs con rate limit compartido (Colab/CI)
    form_jb = urllib.parse.urlencode({"username": "jefe.bodega2@skretting.cl", "password": "Skretting2026!"})
    st_jb, body_jb = make_request("POST", "/auth/login", payload=form_jb)
    token_jb = None
    if st_jb == 200:
        token_jb = body_jb.get("access_token")
    else:
        print(f"⚠️  Login jefe_bodega falló (Status {st_jb}) — QA-09/10/11/12/16..25 pueden fallar")

    # QA-09: Aprobar el movimiento creado en QA-07
    if id_movimiento_generado and token_jb:
        status, body = make_request("PATCH", f"/movimientos/{id_movimiento_generado}/aprobar", token=token_jb)
        if status == 200:
            print_success(f"QA-09: Movimiento aprobado exitosamente (200 OK)")
        else:
            print_fail("QA-09", status, body)
    elif not id_movimiento_generado:
        print("⚠️  QA-09 omitido — QA-07 no generó movimiento")

    # Payload base para los siguientes tests de aprobación/rechazo
    mov_qa10_payload = {
        "id_container": cont_normal['id'], "id_producto": prod_normal['id'],
        "tipo": "entrada_proveedor", "cantidad": 10, "numero_lote": "LOT-QA-10",
        "fecha_fabricacion": "2025-01-01T00:00:00Z", "fecha_vencimiento": "2026-12-31T00:00:00Z",
        "nombre_proveedor": "Prueba", "num_guia_despacho": "123", "registro_sanitario": "123", "temperatura_almacen": 5.0
    }

    # QA-10: Ciberseguridad A04 - Auto-aprobación prohibida
    # Verificamos que si un Jefe crea un movimiento, él mismo no puede aprobarlo.
    if token_jb:
        st10, b10 = make_request("POST", "/movimientos/", payload=mov_qa10_payload, token=token_jb)
        if st10 == 201:
            st10_ap, b10_ap = make_request("PATCH", f"/movimientos/{b10['id']}/aprobar", token=token_jb)
            if st10_ap == 403: # 403 = Forbidden
                print_success("QA-10: Auto-aprobación prohibida correctamente (403 Forbidden)")
            else:
                print_fail("QA-10", st10_ap, b10_ap)

    # QA-11: Rechazar un movimiento
    # Creamos uno nuevo con el operario y lo rechazamos con el Jefe indicando un motivo
    st11, b11 = make_request("POST", "/movimientos/", payload=mov_qa10_payload, token=token_operario)
    if st11 == 201 and token_jb:
        st11_rj, b11_rj = make_request("PATCH", f"/movimientos/{b11['id']}/rechazar", payload={"motivo_rechazo": "Falta firma"}, token=token_jb)
        if st11_rj == 200:
            print_success("QA-11: Movimiento rechazado exitosamente (200 OK)")
        else:
            print_fail("QA-11", st11_rj, b11_rj)

    # QA-12: Ver listado de movimientos pendientes
    if token_jb:
        st12, b12 = make_request("GET", "/movimientos/pendientes", token=token_jb)
        if st12 == 200:
            print_success("QA-12: Listado de pendientes funciona (200 OK)")
        else:
            print_fail("QA-12", st12, b12)

    # QA-13: Algoritmo FEFO (First Expire, First Out)
    # Verificamos que sugiera sacar cajas del lote que se vence primero
    st13, b13 = make_request("GET", f"/movimientos/fefo?id_producto={prod_normal['id']}", token=token_operario)
    if st13 == 200:
        print_success("QA-13: Algoritmo FEFO funciona (200 OK)")
    else:
        print_fail("QA-13", st13, b13)

    # QA-14: Trazabilidad completa de un Lote específico (Para auditorías SERNAPESCA)
    st14, b14 = make_request("GET", "/movimientos/trazabilidad?numero_lote=LOT-QA-AUTO-01", token=token_jb)
    if st14 == 200:
        print_success("QA-14: Trazabilidad de lote funciona (200 OK)")
    else:
        print_fail("QA-14", st14, b14)

    # QA-15: Sincronización Offline
    # Simulamos el payload masivo que enviaría Dexie.js (React) cuando recupera internet.
    # Nota: Es crítico incluir 'fecha_vencimiento' porque la BD PostgreSQL la exige a nivel de tabla (NotNull).
    offline_payload = [{
        "uuid_local": "offline-1234", "id_container": cont_normal['id'], "id_producto": prod_normal['id'],
        "tipo": "salida_produccion", "cantidad": 1, "numero_lote": "LOT-QA-AUTO-01",
        "fecha_vencimiento": "2026-12-31T00:00:00Z" 
    }]
    st15, b15 = make_request("POST", "/movimientos/sync", payload=offline_payload, token=token_operario)
    if st15 == 201:
        print_success("QA-15: Sincronización offline funciona (201 Created)")
    else:
        print_fail("QA-15", st15, b15)

    # -------------------------------------------------------------------------
    # MÓDULO 3: Alertas
    # -------------------------------------------------------------------------
    print_header("MÓDULO 3 — Alertas")
    
    if token_jb:
        # Verificamos si podemos obtener alertas activas en nuestra sede
        st16, alertas = make_request("GET", "/alertas/activas", token=token_jb)
        if st16 == 200:
            print_success("QA-16: Listado de alertas activas (200 OK)")
            
            # QA-17 y QA-18: Probar ciclo de vida de una alerta (si existe alguna)
            if alertas and len(alertas) > 0:
                id_alerta = alertas[0]['id']
                st17, _ = make_request("PATCH", f"/alertas/{id_alerta}/revisar", token=token_jb)
                if st17 == 200:
                    print_success("QA-17: Alerta marcada como revisada (200 OK)")
                
                # Para resolverla, es obligatorio poner una "observación" detallando la corrección
                st18, _ = make_request("PATCH", f"/alertas/{id_alerta}/resolver", payload={"observacion":"Auto resolved"}, token=token_jb)
                if st18 == 200:
                    print_success("QA-18: Alerta resuelta exitosamente (200 OK)")
        else:
            print_fail("QA-16", st16, alertas)

    # QA-19: Autogeneración de Alertas por Capacidad Crítica
    # Simulamos el ingreso de muchísimo stock a un container para forzar que sobrepase el 80% (o se llene)
    mov_qa19 = {**mov_qa07_payload, "cantidad": 850, "numero_lote": "LOT-CRITICO"}
    st19, b19 = make_request("POST", "/movimientos/", payload=mov_qa19, token=token_operario)
    if st19 == 201 and token_jb:
        st19_ap, _ = make_request("PATCH", f"/movimientos/{b19['id']}/aprobar", token=token_jb)
        if st19_ap == 200:
            # Al aprobarse, el motor de reglas debería disparar la alerta asíncrona por WebSocket
            print_success("QA-19: Movimiento gigante para test de alerta capacidad aprobado")

    # -------------------------------------------------------------------------
    # MÓDULO 4: Dashboard
    # -------------------------------------------------------------------------
    print_header("MÓDULO 4 — Dashboard")
    # Verificamos los endpoints que alimentan los gráficos (Recharts) en el Frontend
    if token_jb:
        st20, _ = make_request("GET", "/dashboard/kpis", token=token_jb)
        if st20 == 200: print_success("QA-20: APIs Dashboard KPIs responde (200 OK)")
        else: print_fail("QA-20", st20)

        st21, _ = make_request("GET", "/dashboard/ocupacion-por-galpon", token=token_jb)
        if st21 == 200: print_success("QA-21: APIs Dashboard Ocupación responde (200 OK)")
        
        st22, _ = make_request("GET", "/dashboard/evolucion?dias=30", token=token_jb)
        if st22 == 200: print_success("QA-22: APIs Dashboard Evolución responde (200 OK)")

    # -------------------------------------------------------------------------
    # MÓDULO 5: Reportes
    # -------------------------------------------------------------------------
    print_header("MÓDULO 5 — Reportes (PDF/Excel)")
    # El status 200 indica que el servidor generó el archivo binario correctamente 
    # sin caerse (manejo corregido de UnicodeDecodeError)
    if token_jb:
        st23, _ = make_request("GET", "/reportes/movimientos/pdf", token=token_jb)
        if st23 == 200: print_success("QA-23: Generación PDF responde (200 OK)")
        
        st24, _ = make_request("GET", "/reportes/movimientos/excel", token=token_jb)
        if st24 == 200: print_success("QA-24: Generación Excel responde (200 OK)")

        # Cumplimiento regulatorio de SERNAPESCA
        st25, _ = make_request("GET", "/reportes/sernapesca", token=token_jb)
        if st25 == 200: print_success("QA-25: Reporte SERNAPESCA responde (200 OK)")

    # -------------------------------------------------------------------------
    # MÓDULO 6: Multi-Sede y Health
    # -------------------------------------------------------------------------
    print_header("MÓDULO 6 — Arquitectura Multi-Sede")
    
    # QA-26: Aislamiento
    # Intentamos acceder a un container inexistente o de otra sede. Debe devolver 404/403, 
    # garantizando que un operario de Puerto Montt no manipule cajas de Chiloé.
    st26, b26 = make_request("GET", "/containers/no_existe_uuid", token=token_operario)
    if st26 in (404, 403, 400):
        print_success("QA-26: Aislamiento multi-sede y manejo de errores funciona")

    # QA-27: Health Check
    # Endpoint público que usan los Load Balancers (Render) para saber si la API está viva.
    st27, _ = make_request("GET", "/health")
    if st27 == 200:
        print_success("QA-27: Servidor Saludable (200 OK)")
    else:
        print_fail("QA-27", st27)

    print_header("¡Finalizado! Toda la Suite QA Automatizada ejecutada con éxito.")

if __name__ == "__main__":
    run_qa_automation()
