# Guía de QA — Backend AXIOUS
## Sistema de Inventario 3D Salmonera · Skretting Chile Ltda.

> [!NOTE]
> Esta guía está pensada para el tester de QA. No se necesita acceso al código fuente. Solo se necesita un cliente HTTP (Postman, Insomnia, o el Swagger en `/docs`) y acceso al servidor.

---

## 1. Setup Inicial

### 1.1 Levantar el servidor (si no está corriendo)

```bash
cd inventario-salmonera/backend

# Activar entorno virtual
.\venv\Scripts\activate          # Windows
source venv/bin/activate         # Linux/Mac

# Levantar servidor de desarrollo
uvicorn app.main:app --reload
# → Servidor en http://localhost:8000
# → Swagger en http://localhost:8000/docs
# → Health check en http://localhost:8000/health
```

> [!IMPORTANT]
> Ejecutar SIEMPRE con 1 solo proceso. Si usas gunicorn: `--workers 1`. Con más workers el scheduler de alertas se duplica.

### 1.2 Verificar que el servidor responde

```http
GET http://localhost:8000/health

Respuesta esperada (200):
{
  "status": "ok",
  "environment": "development",
  "version": "3.0.0",
  "websocket_connections": 0,
  "scheduler_running": true
}
```

### 1.3 Verificar suite de tests automatizados

```bash
# Esto prueba 82 escenarios automáticamente en ~2 segundos
pytest tests/ -v
# Resultado esperado: 82 passed, 0 failed
```

---

## 2. Credenciales de Prueba

> [!CAUTION]
> Las credenciales de prueba se crean con el script `scripts/seed.py`. Si la BD está vacía, correr primero:
> ```bash
> python scripts/seed.py
> ```

Credenciales estándar de seed (ajustar según lo que genere seed.py):

| Rol | Email | Contraseña | Restricción |
|-----|-------|-----------|-------------|
| `super_admin` | `admin@skretting.cl` | `Admin1234!` | Sin restricciones |
| `admin_sede` | `admin.sede@skretting.cl` | `Admin1234!` | Solo su sede |
| `jefe_bodega` | `jefe@skretting.cl` | `Admin1234!` | Solo su sede |
| `operario` | `operario@skretting.cl` | `Admin1234!` | Solo crear movimientos |
| `gerencia` | `gerencia@skretting.cl` | `Admin1234!` | Solo lectura / dashboard |

---

## 3. Flujo 1 — Autenticación y Sesión

### TC-01: Login exitoso

```http
POST /auth/login
Content-Type: application/x-www-form-urlencoded

username=jefe@skretting.cl&password=Admin1234!
```

**Resultado esperado: 200 OK**
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "refresh_token": "eyJ..."
}
```

Guardar el `access_token` para usarlo como `Bearer` en todos los siguientes requests.

---

### TC-02: Login con contraseña incorrecta

```http
POST /auth/login
username=jefe@skretting.cl&password=ContraseñaMal
```

**Resultado esperado: 401**
```json
{ "detail": "Credenciales incorrectas" }
```

---

### TC-03: Verificar que el RUT NO aparece en el perfil

```http
GET /auth/me
Authorization: Bearer {token}
```

**Resultado esperado: 200 — el campo `rut` NO debe estar en la respuesta**
```json
{
  "id": "...",
  "nombre": "...",
  "email": "...",
  "codigo_empleado": "JB001",
  "rol": "jefe_bodega"
  // ⚠️ NO debe existir el campo "rut"
}
```

---

### TC-04: Acceso sin token → 401

```http
GET /auth/me
// Sin Authorization header
```

**Resultado esperado: 401**

---

### TC-05: Refresh de token

```http
POST /auth/refresh
Content-Type: application/json

{ "refresh_token": "{refresh_token_del_login}" }
```

**Resultado esperado: 200 con nuevo `access_token`**

---

## 4. Flujo 2 — Movimiento Completo (flujo crítico)

Este es el flujo más importante. Prueba el corazón del sistema.

### TC-06: Registrar movimiento de entrada

```http
POST /movimientos/
Authorization: Bearer {token_operario}
Content-Type: application/json

{
  "id_container": "{uuid_container}",
  "id_producto": "{uuid_producto}",
  "tipo": "entrada_proveedor",
  "cantidad": 100.0,
  "numero_lote": "LOT-QA-001",
  "fecha_fabricacion": "2026-04-01T00:00:00",
  "fecha_vencimiento": "2026-10-01T00:00:00",
  "nombre_proveedor": "BioMar Chile",
  "num_guia_despacho": "GD-QA-001",
  "registro_sanitario": "RS-001",
  "temperatura_almacen": -2.5
}
```

**Resultado esperado: 201 — estado = `pendiente`**

---

### TC-07: Campos SERNAPESCA obligatorios — falta uno

Enviar el mismo request pero **sin** `fecha_vencimiento`:

**Resultado esperado: 422 Unprocessable Entity**
```json
{ "detail": [{ "msg": "fecha_vencimiento requerida por SERNAPESCA..." }] }
```

---

### TC-08: Operario intenta aprobar → 403

```http
PATCH /movimientos/{id}/aprobar
Authorization: Bearer {token_operario}
```

**Resultado esperado: 403 Forbidden**

---

### TC-09: Jefe aprueba movimiento → alerta automática

```http
PATCH /movimientos/{id}/aprobar
Authorization: Bearer {token_jefe}
```

**Resultado esperado: 200 — estado = `aprobado`**

Luego verificar que se generaron alertas:
```http
GET /alertas/activas
Authorization: Bearer {token_jefe}
```

Si el container quedó al ≥80% → debe aparecer alerta `capacidad_critica`.

---

### TC-10: Inmutabilidad — modificar movimiento aprobado

Intentar modificar un movimiento aprobado directamente en la BD (o via trigger):

```sql
-- En psql/pgAdmin:
UPDATE movimiento SET cantidad = 999 WHERE id = '{id_aprobado}';
```

**Resultado esperado: ERROR — el trigger SQL bloquea la operación con mensaje de inmutabilidad.**

---

## 5. Flujo 3 — FEFO y Trazabilidad

### TC-11: FEFO — sugerencia de container por vencimiento

```http
GET /movimientos/fefo?id_producto={uuid}&id_sede={uuid}
Authorization: Bearer {token}
```

**Resultado esperado: 200 — lista de containers ordenados por `fecha_vencimiento ASC` (el que vence antes primero)**

---

### TC-12: Trazabilidad de lote

```http
GET /movimientos/trazabilidad?numero_lote=LOT-QA-001
Authorization: Bearer {token_jefe}
```

**Resultado esperado: 200 — historial completo del lote con:**
- Movimientos en orden cronológico
- `codigo_empleado` presente
- **`rut` NO presente en ningún campo**

---

### TC-13: Trazabilidad — operario → 403

```http
GET /movimientos/trazabilidad?numero_lote=LOT-QA-001
Authorization: Bearer {token_operario}
```

**Resultado esperado: 403**

---

### TC-14: Ruta de picking

```http
GET /movimientos/ruta-picking?containers={id1},{id2},{id3}
Authorization: Bearer {token}
```

**Resultado esperado: 200 — lista de containers con `distancia_desde_anterior` calculada. La ruta optimizada debe tener distancia total menor que el orden original.**

---

## 6. Flujo 4 — Alertas

### TC-15: Ver alertas activas

```http
GET /alertas/activas
Authorization: Bearer {token_jefe}
```

**Resultado esperado: 200 — lista de alertas con `estado = "activa"` de la sede**

---

### TC-16: Revisar alerta

```http
PATCH /alertas/{id}/revisar
Authorization: Bearer {token_jefe}
```

**Resultado esperado: 200 — `estado = "revisada"`, `id_usuario_revision` = id del jefe, `fecha_revision` no nulo**

---

### TC-17: Resolver alerta

```http
PATCH /alertas/{id}/resolver
Authorization: Bearer {token_jefe}
Content-Type: application/json

{ "observacion": "Producto reubicado a container con más capacidad." }
```

**Resultado esperado: 200 — `estado = "resuelta"`**

---

### TC-18: Flujo incorrecto — resolver sin revisar primero

```http
PATCH /alertas/{id_activa}/resolver
Authorization: Bearer {token_jefe}
```

**Resultado esperado: 400 Bad Request**
```json
{ "detail": "Solo se pueden resolver alertas revisadas. Estado actual: activa" }
```

---

### TC-19: Aislamiento de sede — jefe no ve alertas de otra sede

1. Loguearse como jefe de **Sede A**.
2. Verificar que `GET /alertas/activas` NO retorna alertas de la **Sede B**.

**Resultado esperado: lista vacía o solo alertas de la Sede A**

---

### TC-20: Historial paginado

```http
GET /alertas/historial?page=1&size=5&tipo=capacidad_critica
Authorization: Bearer {token_jefe}
```

**Resultado esperado: 200 — estructura con `items`, `total`, `page`, `size`, `pages`**

---

## 7. Flujo 5 — Dashboard

### TC-21: KPIs básicos

```http
GET /dashboard/kpis
Authorization: Bearer {token_jefe}
```

**Resultado esperado: 200**
```json
{
  "ocupacion_global_pct": 45.2,
  "alertas_activas": 3,
  "movimientos_hoy": 7,
  "proximo_vencimiento_dias": 12
}
```

---

### TC-22: Ocupación por galpón

```http
GET /dashboard/ocupacion-por-galpon
Authorization: Bearer {token_jefe}
```

**Resultado esperado: 200 — lista con `name`, `ocupacion_pct`, y `estado` ∈ {`disponible`, `medio`, `critico`}**

Verificar que:
- Galpones al >80% tienen `estado = "critico"`
- Galpones entre 50-80% tienen `estado = "medio"`
- Galpones al ≤50% tienen `estado = "disponible"`

---

### TC-23: Evolución — parámetro días

```http
GET /dashboard/evolucion?dias=7
Authorization: Bearer {token_jefe}
```

**Resultado esperado: 200 — máximo 7 items, cada uno con `fecha`, `movimientos`, `entradas`, `salidas`**

```http
GET /dashboard/evolucion?dias=0
```

**Resultado esperado: 422 — días mínimo es 1**

---

### TC-24: Gerencia puede ver dashboard

```http
GET /dashboard/kpis
Authorization: Bearer {token_gerencia}
```

**Resultado esperado: 200** (gerencia tiene acceso de solo lectura al dashboard)

---

## 8. Flujo 6 — Reportes y Exportaciones

### TC-25: Descargar PDF

```http
GET /reportes/movimientos/pdf?dias=30
Authorization: Bearer {token_jefe}
```

**Resultado esperado:**
- Status 200
- `Content-Type: application/pdf`
- `Content-Disposition: attachment; filename="movimientos_skretting_...pdf"`
- El archivo al abrirlo debe mostrar header "Skretting Chile Ltda.", tabla con columnas SERNAPESCA
- **El RUT no debe aparecer en ninguna columna**

---

### TC-26: Descargar Excel

```http
GET /reportes/movimientos/excel?dias=30
Authorization: Bearer {token_jefe}
```

**Resultado esperado:**
- Status 200
- `Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- Archivo `.xlsx` abrible en Excel/LibreOffice
- Fila 4 = cabeceras con "Operario (Código)" — **NO "RUT"**
- Fila 5 en adelante = datos de movimientos

---

### TC-27: Reporte SERNAPESCA — sin RUT

```http
GET /reportes/sernapesca?dias=30
Authorization: Bearer {token_admin_sede}
```

**Resultado esperado:**
- Status 200
- Excel con header verde institucional
- Columna "Código Operario" presente
- **La columna "RUT" NO debe existir en ninguna parte del archivo**

---

### TC-28: Operario no puede exportar → 403

```http
GET /reportes/movimientos/pdf
Authorization: Bearer {token_operario}
```

**Resultado esperado: 403 Forbidden**

---

### TC-29: Filtro de fechas

```http
GET /reportes/movimientos/excel?desde=2026-01-01&hasta=2026-01-31
Authorization: Bearer {token_jefe}
```

**Resultado esperado: 200 — Excel con movimientos solo del mes de enero 2026**

---

## 9. Flujo 7 — WebSocket (Tiempo Real)

### TC-30: Conectarse al WebSocket

Usar [wscat](https://github.com/websockets/wscat) o Postman WebSocket:

```bash
# Instalar wscat si no está
npm install -g wscat

# Conectarse (reemplazar {id_sede} con un UUID real)
wscat -c ws://localhost:8000/ws/alertas/{id_sede}
```

**Resultado esperado: conexión aceptada sin errores**

---

### TC-31: Recibir alerta en tiempo real

1. Mantener la conexión WebSocket abierta del TC-30
2. En otra ventana, aprobar un movimiento que lleve un container al >80%:
   ```http
   PATCH /movimientos/{id}/aprobar
   Authorization: Bearer {token_jefe}
   ```
3. Verificar que en la ventana del WebSocket llega automáticamente:

```json
{
  "evento": "nueva_alerta",
  "alerta": {
    "tipo": "capacidad_critica",
    "severidad": "critica",
    "descripcion": "Container G1-C04 al 85%...",
    "id_container": "...",
    "container_codigo": "G1-C04"
  }
}
```

---

## 10. Pruebas de Seguridad y Borde

### TC-32: Token expirado → 401

Esperar que el token expire (60 minutos) o modificar `exp` del JWT:

**Resultado esperado: 401 Unauthorized**

---

### TC-33: Token manipulado → 401

```http
GET /auth/me
Authorization: Bearer {token_valido}MANGLED
```

**Resultado esperado: 401**

---

### TC-34: Paginación — valores inválidos → 422

```http
GET /containers/?page=0&size=200
```

**Resultado esperado: 422** (page mínimo 1, size máximo 100)

---

### TC-35: Sync offline — container sin capacidad

```http
POST /movimientos/sync
Authorization: Bearer {token_operario}
Content-Type: application/json

{
  "movimientos": [
    {
      "uuid_local": "local-001",
      "id_container": "{container_lleno}",
      "id_producto": "{uuid}",
      "tipo": "entrada_proveedor",
      "cantidad": 999999,
      "numero_lote": "SYNC-001",
      "fecha_vencimiento": "2026-12-01T00:00:00",
      "nombre_proveedor": "Test",
      "num_guia_despacho": "GD-SYNC",
      "registro_sanitario": "RS-SYNC",
      "temperatura_almacen": -2.0
    }
  ]
}
```

**Resultado esperado: 201 con `accion: "rechazar"` y motivo de capacidad excedida**

---

### TC-36: Swagger deshabilitado en producción

Cuando el `.env` tiene `ENVIRONMENT=production`:

```http
GET /docs
GET /redoc
```

**Resultado esperado: 404** (Swagger no está disponible en producción)

---

## 11. Checklist de Cumplimiento Normativo

Marcar cada ítem luego de verificarlo:

- [ ] `GET /auth/me` → NO contiene campo `rut`
- [ ] `GET /movimientos/trazabilidad` → NO contiene campo `rut`
- [ ] `GET /alertas/activas` → NO contiene campo `rut`
- [ ] `GET /reportes/movimientos/pdf` → PDF sin columna ni dato de RUT
- [ ] `GET /reportes/movimientos/excel` → Excel sin columna ni dato de RUT
- [ ] `GET /reportes/sernapesca` → Excel sin columna "RUT", con "Código Operario"
- [ ] `POST /movimientos/` con tipo `entrada_proveedor` y sin `fecha_vencimiento` → **422**
- [ ] `POST /movimientos/` con tipo `entrada_proveedor` y sin `nombre_proveedor` → **422**
- [ ] `POST /movimientos/` con tipo `entrada_proveedor` y sin `num_guia_despacho` → **422**
- [ ] `UPDATE movimiento` en SQL directo → **ERROR de trigger**

---

## 12. Plantilla de Reporte de Bug

Usar esta plantilla para reportar cualquier comportamiento incorrecto:

```
BUG-XXX: [Título descriptivo]

Ambiente: development / staging / production
Fecha: YYYY-MM-DD
Tester: [Nombre]

PASOS PARA REPRODUCIR:
1. Login como {rol}
2. Enviar POST/GET/PATCH a {endpoint}
3. Con payload: {json}

RESULTADO OBTENIDO:
HTTP {status}
{response body}

RESULTADO ESPERADO:
HTTP {status esperado}
{descripción del comportamiento correcto}

SEVERIDAD: Crítico / Alto / Medio / Bajo
MÓDULO AFECTADO: Auth / Movimientos / Alertas / Dashboard / Reportes
```

---

## 13. Endpoints de Referencia Rápida

| URL | Descripción |
|-----|-------------|
| `http://localhost:8000/docs` | Swagger UI interactivo (solo en development) |
| `http://localhost:8000/redoc` | Documentación alternativa ReDoc |
| `http://localhost:8000/health` | Health check del sistema |
| `http://localhost:8000/openapi.json` | Schema OpenAPI en JSON |

---

*Guía de QA — AXIOUS Backend v3.0.0 — INACAP Puerto Montt 2026*
*Esta guía cubre 36 casos de prueba manuales distribuidos en 7 flujos principales.*
