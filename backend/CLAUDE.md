# 🐟 Senior Backend — Sistema de Inventario 3D Salmonera
# Skill personalizada para Claude Code
# Proyecto: Gueremy Barrientos · Bastián Riffo · Sebastián Bravo — INACAP 2026

---

## Contexto del Proyecto

Sistema web de gestión de inventario con visualización 3D interactiva para
**Skretting**, empresa salmonera de la Región de Los Lagos, Chile.

- **Cliente real**: Skretting (empresa salmonera colaboradora)
- **Problema**: Inventario gestionado en Excel compartido sin visibilidad
  espacial ni trazabilidad. +1.000 hrs/año perdidas por sede.
- **Solución**: App web 3D multi-sede con 5 roles, offline en pontones,
  cumplimiento SERNAPESCA automático y capa BI integrada.

---

## Stack Tecnológico (NO cambiar sin consultar)

```
Backend  : FastAPI 0.110+ · Python 3.11+ · SQLAlchemy 2.x async · Alembic
Auth     : python-jose (JWT HS256) · passlib[bcrypt] (cost=12)
BD       : PostgreSQL 15+ · asyncpg (driver async)
WS       : FastAPI WebSockets nativo (sin Django Channels ni Redis)
Scheduler: APScheduler 3.x (ETL nocturno + alertas programadas)
Reportes : reportlab (PDF) · openpyxl (Excel)
Deploy   : DigitalOcean Droplet São Paulo · Nginx · Gunicorn + Uvicorn
```

---

## Estructura de Carpetas (respetar siempre)

```
backend/
├── app/
│   ├── api/           # Routers FastAPI — 1 archivo por entidad
│   │   ├── auth.py
│   │   ├── sedes.py
│   │   ├── galpones.py
│   │   ├── containers.py
│   │   ├── productos.py
│   │   ├── usuarios.py
│   │   ├── movimientos.py
│   │   ├── alertas.py
│   │   ├── dashboard.py
│   │   └── reportes.py
│   ├── models/        # SQLAlchemy ORM — 1 archivo por entidad
│   │   ├── sede.py · galpon.py · container.py · producto.py
│   │   ├── usuario.py · movimiento.py · alerta.py
│   │   └── __init__.py  ← importa todos los modelos
│   ├── schemas/       # Pydantic v2 — separar Create/Read/Update
│   ├── services/      # Lógica de negocio — NO en los routers
│   │   ├── alertas.py    # Motor de alertas
│   │   ├── fefo.py       # Algoritmo FEFO
│   │   ├── picking.py    # Optimización ruta galpón
│   │   ├── sync.py       # Resolución conflictos offline
│   │   └── etl.py        # ETL nocturno para DWH
│   ├── core/
│   │   ├── config.py     # pydantic-settings desde .env
│   │   ├── security.py   # JWT, bcrypt, guards
│   │   └── database.py   # engine async, Base, get_db
│   └── main.py
├── alembic/
├── scripts/
│   ├── seed.py           # Datos de prueba completos
│   ├── api_scaffolder.py
│   ├── database_migration_tool.py
│   └── api_load_tester.py
├── tests/
├── .env                  # NUNCA commitear
├── .env.example          # SÍ commitear (sin valores reales)
├── requirements.txt      # Versiones fijadas (sin ^)
└── CLAUDE.md             # Este archivo
```

---

## Modelos de Base de Datos (9 tablas)

```
sede          → tipo: ponton | planta | bodega
galpon        → FK sede, filas, columnas (grilla 3D)
container     → FK galpon, posicion_fila, posicion_col, estado (5 valores)
producto      → categoria: alimento | quimico | veterinario | equipo | repuesto | general
usuario       → rol: super_admin | admin_sede | jefe_bodega | operario | gerencia
usuario_galpon→ PIVOT N:M usuario ↔ galpon
movimiento    → INMUTABLE (trigger PostgreSQL)
alerta        → 8 tipos, 3 severidades
log_auditoria → toda acción crítica queda registrada
```

### Estados del Container (sistema de 5 colores)
```
disponible   → verde  (0-40% ocupación)
medio        → amarillo (41-79%)
critico      → rojo   (80-100%)
mantenimiento→ gris   (manual)
cuarentena   → morado (SERNAPESCA o calidad)
```

---

## ⚠️ REGLAS CRÍTICAS — Nunca violar

### 1. LEY 19.628 — Protección de datos personales
```python
# El RUT de operarios y proveedores es INTERNO ÚNICAMENTE
# NUNCA debe aparecer en:
#   - Ningún response schema de la API
#   - Logs de Nginx o de la aplicación
#   - Reportes externos
#   - Mensajes de error
# En reportes externos usar SIEMPRE: codigo_empleado

# ✅ CORRECTO
class UsuarioRead(BaseModel):
    id: str
    nombre: str
    email: str
    codigo_empleado: str  # aparece en reportes
    rol: RolEnum
    # rut: str  ← JAMÁS en responses

# ❌ INCORRECTO
class UsuarioRead(BaseModel):
    rut: str  # Viola Ley 19.628
```

### 2. INMUTABILIDAD de movimientos (SERNAPESCA)
```python
# Los movimientos NUNCA se editan ni eliminan
# El trigger PostgreSQL bloquea UPDATE y DELETE
# Para corregir un error → registrar un movimiento tipo "correccion"
# con id_movimiento_original apuntando al registro con error

# ✅ CORRECTO
nuevo = Movimiento(
    tipo="correccion",
    id_movimiento_original="uuid-del-movimiento-erróneo",
    observaciones="Corrección: cantidad era 50kg, no 500kg"
)

# ❌ INCORRECTO
await db.execute(
    update(Movimiento).where(Movimiento.id == id)  # Trigger lo rechazará
)
```

### 3. Jefe de bodega NO aprueba sus propios movimientos
```python
# Control de auditoría obligatorio en PATCH /movimientos/{id}/aprobar
@router.patch("/{id}/aprobar")
async def aprobar_movimiento(id: str, current_user: Usuario = Depends(require_role(["jefe_bodega", "super_admin"]))):
    mov = await get_movimiento(id)
    if mov.id_usuario == current_user.id:
        raise HTTPException(
            status_code=403,
            detail="No puedes aprobar movimientos que tú mismo registraste."
        )
```

### 4. Campos SERNAPESCA obligatorios en entradas
```python
# Para tipo="entrada_proveedor" son OBLIGATORIOS:
SERNAPESCA_REQUIRED = [
    "numero_lote",
    "fecha_vencimiento",
    "nombre_proveedor",
    "num_guia_despacho",
    "registro_sanitario",
    "temperatura_almacen",
]
# Para productos veterinarios agregar:
SAG_REQUIRED = ["num_receta_retenida", "num_autorizacion_sag"]

# Validar con @field_validator en el schema
```

### 5. Separación de productos (alimento ≠ químico)
```python
# Al registrar un movimiento de entrada, validar que
# el tipo de producto NO conflicte con el container
INCOMPATIBLE = {
    "alimento": ["quimico"],
    "quimico":  ["alimento", "veterinario"],
}

def validar_compatibilidad(tipo_producto: str, tipo_permitido_container: str):
    if tipo_producto in INCOMPATIBLE.get(tipo_permitido_container, []):
        raise HTTPException(400,
            f"El container no permite {tipo_producto} junto a {tipo_permitido_container}")
```

### 6. Aislamiento multi-tenant
```python
# Cada query que accede a containers/galpones/usuarios SIEMPRE
# debe filtrar por id_sede del usuario autenticado.
# NUNCA devolver datos de otra sede, aunque el id sea correcto.

stmt = select(Container).where(
    Container.id == container_id,
    Container.galpon.has(Galpon.id_sede == current_user.id_sede)  # AISLAMIENTO
)
```

---

## Algoritmos del Proyecto

### FEFO — First Expired, First Out (app/services/fefo.py)
```python
# Al sugerir de qué container sacar un producto,
# ordenar por fecha_vencimiento ASC (el que vence antes, sale primero)
# Reducir mermas del 1.5% actual → objetivo < 1%

async def sugerir_container_fefo(db, id_producto, id_sede):
    stmt = (
        select(Container.id, Container.codigo,
               Movimiento.fecha_vencimiento, Movimiento.numero_lote)
        .join(Movimiento, Movimiento.id_container == Container.id)
        .where(
            Movimiento.id_producto == id_producto,
            Container.galpon.has(Galpon.id_sede == id_sede),
            Container.estado == "disponible",
            Movimiento.estado == "aprobado",
        )
        .order_by(Movimiento.fecha_vencimiento.asc())
        .limit(5)
    )
    return (await db.execute(stmt)).mappings().all()
```

### Optimización de ruta de picking (app/services/picking.py)
```python
# Dado un pedido con N productos en distintos containers,
# calcular el recorrido mínimo en el galpón usando Nearest Neighbor
# Complejidad: O(n²) — aceptable para n < 50 containers/pedido

def distancia_manhattan(a: tuple, b: tuple) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])

def optimizar_ruta(containers: list[dict], inicio=(0,0)) -> list[dict]:
    pendientes = containers.copy()
    ruta, pos = [], inicio
    while pendientes:
        mas_cercano = min(pendientes,
            key=lambda c: distancia_manhattan(pos, (c["fila"], c["col"])))
        ruta.append(mas_cercano)
        pos = (mas_cercano["fila"], mas_cercano["col"])
        pendientes.remove(mas_cercano)
    return ruta
```

### Resolución de conflictos offline (app/services/sync.py)
```python
# Estrategia: Last-Write-Wins con validación de capacidad
# Si el movimiento offline viola la capacidad actual → RECHAZAR

def resolver_conflicto(movimiento_offline: dict, estado_actual_db: dict) -> dict:
    disponible = estado_actual_db["capacidad_max"] - estado_actual_db["ocupacion_actual"]
    if movimiento_offline["tipo"] == "entrada":
        if movimiento_offline["cantidad"] > disponible:
            return {"accion": "rechazar",
                    "motivo": f"Sin capacidad. Disponible: {disponible}"}
    if movimiento_offline["tipo"] == "salida":
        if movimiento_offline["cantidad"] > estado_actual_db["ocupacion_actual"]:
            return {"accion": "rechazar",
                    "motivo": "Stock insuficiente para la salida."}
    return {"accion": "aplicar", "motivo": "OK"}
```

---

## Seguridad y Ciberseguridad (OWASP Top 10)

### Autenticación (A07)
```python
# JWT con HS256 — NUNCA usar ECDSA (CVE-2024-33663 en python-jose)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 7

# bcrypt con cost factor 12 mínimo
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto",
                            bcrypt__rounds=12)
```

### Rate Limiting en login (A07)
```python
# Máximo 5 intentos de login por IP cada 5 minutos
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/auth/login")
@limiter.limit("5/5minutes")
async def login(request: Request, ...):
    ...
```

### Sanitización de inputs (A03 — Injection)
```python
# Usar SIEMPRE parámetros bindados en SQLAlchemy
# NUNCA construir queries con f-strings o concatenación

# ✅ CORRECTO (SQLAlchemy ORM)
stmt = select(Movimiento).where(Movimiento.numero_lote == numero_lote)

# ❌ INCORRECTO (vulnerable a SQL injection)
stmt = text(f"SELECT * FROM movimiento WHERE numero_lote = '{numero_lote}'")
```

### Validación estricta de inputs (A03)
```python
import re
from pydantic import field_validator

class MovimientoCreate(BaseModel):
    numero_lote: str

    @field_validator("numero_lote")
    @classmethod
    def validar_lote(cls, v):
        v = v.strip().upper()
        if not re.match(r'^[A-Za-z0-9\-\.]{1,50}$', v):
            raise ValueError("Número de lote con caracteres inválidos")
        return v
```

### Headers de seguridad en Nginx
```nginx
# /etc/nginx/sites-available/salmonera
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "DENY" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;

# Deshabilitar Swagger en producción
location /docs    { return 404; }
location /redoc   { return 404; }
location /openapi.json { return 404; }
```

### Manejo seguro de secretos
```python
# NUNCA hardcodear credenciales en el código
# SIEMPRE leer desde variables de entorno con pydantic-settings

class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str        # mínimo 32 caracteres aleatorios
    ENVIRONMENT: str = "development"

    model_config = ConfigDict(env_file=".env")

# Generar SECRET_KEY seguro:
# python -c "import secrets; print(secrets.token_hex(32))"
```

---

## Optimización de Base de Datos

### Índices obligatorios (crear en migración Alembic)
```sql
-- Búsqueda de lote SERNAPESCA (fiscalizaciones frecuentes)
CREATE INDEX CONCURRENTLY idx_movimiento_numero_lote
    ON movimiento (numero_lote);

-- Búsqueda full-text por lote
CREATE INDEX CONCURRENTLY idx_movimiento_lote_gin
    ON movimiento USING gin(to_tsvector('spanish', numero_lote));

-- Alertas activas por sede (dashboard tiempo real)
CREATE INDEX CONCURRENTLY idx_alerta_activa
    ON alerta (id_container, estado) WHERE estado = 'activa';

-- Movimientos por container y fecha (historial)
CREATE INDEX CONCURRENTLY idx_movimiento_container_fecha
    ON movimiento (id_container, fecha_hora DESC);

-- Containers por galpón y estado (render 3D)
CREATE INDEX CONCURRENTLY idx_container_galpon_estado
    ON container (id_galpon, estado);

-- Movimientos pendientes (dashboard jefe de bodega)
CREATE INDEX CONCURRENTLY idx_movimiento_pendiente
    ON movimiento (estado, fecha_hora DESC) WHERE estado = 'pendiente';

-- Vencimientos próximos (alertas FEFO)
CREATE INDEX CONCURRENTLY idx_movimiento_vencimiento
    ON movimiento (fecha_vencimiento ASC) WHERE estado = 'aprobado';
```

### Evitar N+1 — usar selectinload siempre
```python
# ✅ CORRECTO — 2 queries en total
stmt = (
    select(Container)
    .options(
        selectinload(Container.galpon).selectinload(Galpon.sede),
        selectinload(Container.alertas),
    )
    .where(Container.id_galpon == id_galpon)
)

# ❌ INCORRECTO — N+1 queries (1 por cada container)
containers = await db.execute(select(Container))
for c in containers.scalars():
    print(c.galpon.nombre)  # lazy load: 1 query extra por iteración
```

### Proyecciones mínimas para el render 3D
```python
# Solo traer los 8 campos que necesita React Three Fiber
# NO usar select(Container) que trae todos los campos
stmt = select(
    Container.id,
    Container.codigo,
    Container.posicion_fila,
    Container.posicion_col,
    Container.ocupacion_actual,
    Container.capacidad_max,
    Container.estado,
    Container.tipo_producto_permitido,
).where(Container.id_galpon == id_galpon)
```

### Caché TTL por tipo de dato
```python
# Datos estables (sedes, galpones) → TanStack Query staleTime largo
# Datos frecuentes (estado containers) → staleTime 30 segundos
# Alertas activas → staleTime 10 segundos
# Tiempo real → WebSockets (no polling)

CACHE_TTL = {
    "sedes_lista":        30 * 60,   # 30 minutos
    "galpones_por_sede":  15 * 60,   # 15 minutos
    "containers_estado":  30,         # 30 segundos
    "alertas_activas":    10,         # 10 segundos
    "movimientos_pendientes": 15,     # 15 segundos
}
```

---

## Manejo de Carga del Servidor

### Configuración Gunicorn para producción
```bash
# Para 50 usuarios activos simultáneos en Droplet 2vCPU/4GB:
gunicorn app.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --worker-connections 100 \
  --timeout 60 \
  --keepalive 5 \
  --bind 0.0.0.0:8000

# IMPORTANTE: Con APScheduler usar --workers 1 en desarrollo
# En producción con múltiples workers, APScheduler se ejecuta N veces
# Solución: solo el worker PID==1 ejecuta el scheduler
```

### Connection Pool de PostgreSQL
```python
# Para 50 usuarios activos con 4 workers:
# pool_size = workers * conexiones_por_worker
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=10,        # conexiones permanentes
    max_overflow=20,     # conexiones extra bajo pico de carga
    pool_timeout=30,     # segundos antes de error por falta de conexión
    pool_recycle=1800,   # reciclar conexiones cada 30 min
    echo=False,          # SIEMPRE False en producción
)
```

### WebSockets — limitar conexiones
```python
# Una conexión WS por usuario, no múltiples tabs
# Al conectar un nuevo cliente con el mismo id_sede,
# no duplicar — el frontend maneja reconexión automática

class ConnectionManager:
    def __init__(self):
        # sede_id → lista de websockets activos
        self.connections: dict[str, list[WebSocket]] = {}

    async def connect(self, ws: WebSocket, id_sede: str):
        await ws.accept()
        self.connections.setdefault(id_sede, []).append(ws)

    async def broadcast_sede(self, id_sede: str, mensaje: dict):
        for ws in self.connections.get(id_sede, []):
            try:
                await ws.send_json(mensaje)
            except:
                self.connections[id_sede].remove(ws)
```

### Escalado por cantidad de clientes
```
1 cliente  (Skretting, ~50 usuarios):
  → Droplet $24/mes (2vCPU, 4GB) · 4 workers · pool_size=10

3 clientes (~150 usuarios):
  → Droplet $48/mes (4vCPU, 8GB) · 8 workers · pool_size=20
  → Separar PostgreSQL a DO Managed Database ($15/mes extra)

5+ clientes (~250 usuarios):
  → 2 Droplets + Load Balancer DO ($12/mes)
  → Multi-tenant con schemas separados por cliente en PostgreSQL
```

---

## Motor de Alertas (8 tipos)

```python
# app/services/alertas.py
# Llamar después de cada movimiento aprobado

ALERTAS_CONFIG = {
    "capacidad_critica":       {"umbral": 80,  "severidad": "critica"},
    "vencimiento_30_dias":     {"dias": 30,    "severidad": "aviso"},
    "vencimiento_7_dias":      {"dias": 7,     "severidad": "critica"},
    "stock_minimo":            {},              # comparar con producto.stock_minimo
    "movimiento_fuera_horario":{},              # comparar con horario_laboral de la sede
    "discrepancia_inventario": {"umbral": 5},  # % diferencia físico vs digital
    "sin_movimiento_30_dias":  {"dias": 30,    "severidad": "informativa"},
    "cuarentena_activa":       {},              # solo informar si container.estado == cuarentena
}

# APScheduler jobs:
# - Cada noche 02:00: evaluar vencimientos y containers sin movimiento
# - Cada 30 min: evaluar discrepancias y stock mínimo
# - Inmediato (post-aprobación): capacidad y horario
```

---

## Schemas Pydantic — Convenciones

```python
# Separar siempre en 3 schemas por entidad
class ContainerCreate(BaseModel):   # POST — solo campos que envía el cliente
    ...

class ContainerRead(BaseModel):     # GET — lo que devuelve la API
    model_config = ConfigDict(from_attributes=True)
    # NUNCA incluir rut, password_hash ni datos sensibles

class ContainerUpdate(BaseModel):   # PATCH — todos los campos opcionales
    ...

# Para paginación usar siempre este patrón:
class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int
    pages: int
```

---

## Endpoints Prioritarios (en este orden)

```
Semana 1: BD + trigger + alembic
Semana 2: POST /auth/login · GET /auth/me · guards por rol
Semana 3: CRUD /sedes · /galpones · /containers
Semana 4: CRUD /usuarios · /productos · GET /containers/{id}/qr
Semana 5: POST /movimientos · PATCH aprobar/rechazar · GET pendientes
Semana 6: GET /movimientos/fefo · /trazabilidad · POST /movimientos/sync
Semana 7: WS /ws/alertas/{sede} · motor alertas · APScheduler
Semana 8: GET /dashboard/kpis · /reportes/pdf · /reportes/excel · seed.py
```

---

## Errores Comunes — Evitar

```python
# ❌ lazy="dynamic" con async SQLAlchemy → error en runtime
# ✅ usar lazy="raise" en modelos + selectinload explícito en queries

# ❌ asyncpg + psycopg2 mezclados en la misma conexión
# ✅ asyncpg para FastAPI, psycopg2-binary solo para alembic/env.py

# ❌ APScheduler con múltiples workers → jobs duplicados
# ✅ en prod: configurar solo 1 worker para el proceso con scheduler

# ❌ Swagger en producción → exposición de la API
# ✅ app = FastAPI(docs_url=None) si ENVIRONMENT == "production"

# ❌ echo=True en producción → logs enormes que llenan el disco
# ✅ echo=settings.ENVIRONMENT == "development"

# ❌ SheetJS versión > 0.18.5 → es de pago
# ✅ fijar exactamente xlsx==0.18.5 en package.json del frontend

# ❌ python-jose con algoritmo ECDSA → CVE-2024-33663
# ✅ usar siempre ALGORITHM = "HS256"
```

---

## Variables de Entorno (.env.example)

```env
# Base de datos
DATABASE_URL=postgresql+asyncpg://salmonera_user:PASSWORD@localhost:5432/salmonera_db
DATABASE_URL_SYNC=postgresql+psycopg2://salmonera_user:PASSWORD@localhost:5432/salmonera_db

# Seguridad — generar con: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=CAMBIAR_POR_32_CARACTERES_ALEATORIOS
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=7

# Entorno
ENVIRONMENT=development  # production en DigitalOcean

# Empresa (multi-tenant fase futura)
TENANT_ID=skretting
```

---

## Checklist antes de cada commit

- [ ] RUT no aparece en ningún response schema
- [ ] Todos los endpoints nuevos tienen `Depends(require_role(...))`
- [ ] Queries con selectinload (sin lazy loading accidental)
- [ ] Campos SERNAPESCA validados en entradas de proveedor
- [ ] Sin credenciales hardcodeadas en el código
- [ ] echo=False si es código de producción
- [ ] Tests escritos para el endpoint nuevo

---

## Ruta de Desarrollo — Orden Obligatorio

> ⚠️ NUNCA saltar pasos. Cada fase depende de la anterior.
> Si Claude Code detecta que falta algo de una fase anterior, debe señalarlo antes de continuar.

### FASE 1 — Fundamentos (Semanas 1-2) ← ESTAMOS AQUÍ
```
✅ S1.1 Setup: entorno virtual, estructura de carpetas, .env
✅ S1.2 Modelos SQLAlchemy: 7 modelos escritos
✅ S1.3 Base de datos: salmonera_db creada en PostgreSQL
⏳ S1.4 Alembic: migración pendiente de ejecutar
⏳ S1.5 Trigger inmutabilidad: pendiente de crear en PostgreSQL
⏳ S1.6 uvicorn corriendo sin errores: pendiente verificar
```

**Antes de pasar a Fase 2, verificar:**
```bash
# Estos comandos deben correr sin errores
alembic upgrade head
uvicorn app.main:app --reload
# Abrir http://localhost:8000/docs y ver Swagger
```

---

### FASE 2 — Autenticación JWT (Semanas 3-4) ← COMPLETADA
```
[x] POST /auth/login → devuelve access_token JWT (HS256)
[x] GET /auth/me → devuelve perfil del usuario autenticado
[x] Dependencia get_current_user que valida el token
[x] Dependencia require_role(roles=[]) que bloquea por rol
[x] Rate limiting en /auth/login: 5 intentos / 5 minutos
[x] POST /auth/register (solo Super Admin)
```

**Antes de pasar a Fase 3, verificar:**
```bash
# En Swagger: hacer login con usuario del seed
# Copiar el token → usarlo en endpoints protegidos
# Un operario intentando acceder a ruta de jefe → debe recibir 403
```

---

### FASE 3 — CRUD Core (Semanas 5-6)
```
[ ] Schemas Pydantic v2 para todas las entidades (Create/Read/Update)
[ ] GET/POST/PATCH/DELETE /sedes (solo Super Admin)
[ ] GET/POST/PATCH /galpones (filtrar por id_sede del token)
[ ] GET/POST/PATCH /containers (filtrar por galpon → sede)
[ ] GET /containers/{id}/qr → imagen QR base64
[ ] GET /containers/{id}/info-publica → datos para escaneo QR
[ ] GET/POST/PATCH /productos
[ ] GET/POST /usuarios + POST /usuarios/{id}/asignar-galpones
```

**Regla de oro de esta fase:**
```python
# TODOS los listados filtran por id_sede del usuario autenticado
# NUNCA devolver datos de otra sede aunque el id sea correcto
# RUT NUNCA en ningún response schema
```

---

### FASE 4 — Movimientos (Semanas 7-8) ← El sprint más importante
```
[ ] POST /movimientos con validaciones:
    - Campos SERNAPESCA obligatorios en tipo=entrada_proveedor
    - Separación alimento ≠ químico
    - No superar capacidad_max del container
    - Fecha vencimiento < 30 días → alerta automática
[ ] Traslados internos → estado=aprobado automático
[ ] Entradas/salidas → estado=pendiente
[ ] PATCH /movimientos/{id}/aprobar (Jefe de Bodega)
    - Validar: id_usuario ≠ id_usuario_aprobador (403 si coinciden)
[ ] PATCH /movimientos/{id}/rechazar (motivo obligatorio)
[ ] GET /movimientos/pendientes (filtrado por sede del jefe)
[ ] Al aprobar: actualizar ocupacion_actual del container
```

---

### FASE 5 — Algoritmos (Semana 9)
```
[ ] GET /movimientos/fefo?id_producto=X&id_sede=Y
    → containers ordenados por fecha_vencimiento ASC
[ ] GET /movimientos/ruta-picking?containers=[]
    → Nearest Neighbor para optimizar recorrido en galpón
[ ] GET /movimientos/trazabilidad?numero_lote=X
    → historial completo del lote (usar índice GIN)
[ ] POST /movimientos/sync
    → recibe lista de movimientos offline, procesa conflictos
```

---

### FASE 6 — Alertas + WebSockets (Semana 10)
```
[ ] Motor de alertas: app/services/alertas.py
    → evaluar_alertas(id_container) con los 8 tipos definidos
    → llamar después de cada movimiento aprobado
[ ] APScheduler nocturno (02:00): vencimientos y sin movimiento
[ ] APScheduler cada 30 min: stock mínimo y discrepancias
[ ] WS /ws/alertas/{id_sede} → tiempo real para jefe de bodega
[ ] Al crear alerta → emitir evento por WebSocket
[ ] PATCH /alertas/{id}/revisar + /resolver
[ ] GET /alertas/activas?id_sede=X
```

---

### FASE 7 — Dashboard + ETL + Reportes (Semana 11)
```
[ ] GET /dashboard/kpis?id_sede=X → cards del dashboard
[ ] GET /dashboard/ocupacion-por-galpon → barras Recharts
[ ] GET /dashboard/evolucion?dias=30 → línea temporal
[ ] GET /dashboard/comparativo-sedes → radar gerencia
[ ] GET /reportes/movimientos/pdf → reportlab con logo
[ ] GET /reportes/movimientos/excel → openpyxl
[ ] GET /reportes/sernapesca → formulario oficial
[ ] APScheduler ETL nocturno → carga DWH para Metabase
```

---

### FASE 8 — Seed + Cierre Backend (Semana 12)
```
[ ] scripts/seed.py completo:
    - 1 empresa (Skretting)
    - 4 sedes (1 pontón, 1 planta, 2 bodegas)
    - 3 galpones por sede
    - 20 containers por galpón
    - 8 usuarios (1 de cada rol + extras)
    - 50 movimientos variados con campos SERNAPESCA
[ ] README.md con instrucciones de instalación
[ ] Checklist pre-frontend completo (ver sección siguiente)
```

---

## Diagnóstico del Sprint Actual

### Estado al 17 de Abril 2026

```
FASE 1 — Fundamentos
  ✅ Python 3.11 instalado
  ✅ PostgreSQL 15 instalado
  ✅ Base de datos salmonera_db creada
  ✅ Usuario salmonera_user creado con privilegios
  ✅ Entorno virtual configurado
  ✅ Dependencias instaladas (requirements.txt)
  ✅ 7 modelos SQLAlchemy escritos:
       sede.py · galpon.py · container.py · producto.py
       usuario.py (+ UsuarioGalpon) · movimiento.py · alerta.py
  ✅ .env configurado con DATABASE_URL y SECRET_KEY
  ✅ app/core/config.py con pydantic-settings
  ✅ app/database.py con engine async y Base declarativa

  ⏳ PENDIENTE INMEDIATO — Semana 1:
       1. Ejecutar: alembic revision --autogenerate -m "create_all_tables"
       2. Ejecutar: alembic upgrade head
       3. Verificar tablas en PostgreSQL: \dt en psql
       4. Crear trigger de inmutabilidad en tabla movimiento
       5. Verificar: uvicorn app.main:app --reload sin errores
       6. Abrir http://localhost:8000/docs → Swagger visible

FASE 2 en adelante → NO EMPEZAR hasta completar los 6 puntos anteriores
```

### Próximos 3 pasos concretos que debe hacer Claude Code

Cuando el usuario abra Claude Code en la carpeta backend, sugerir en este orden:

```
1. "Voy a ejecutar alembic upgrade head para crear las tablas"
   → si falla, revisar DATABASE_URL en .env y conexión a PostgreSQL

2. "Voy a crear el trigger de inmutabilidad en PostgreSQL"
   → ejecutar el SQL del trigger directamente via psycopg2

3. "Voy a verificar que uvicorn levanta sin errores"
   → si hay errores de importación, revisar app/models/__init__.py
```

---

## Instrucción para Claude Code al iniciar sesión

Al comenzar cualquier sesión en este proyecto, Claude Code debe:

1. Leer este CLAUDE.md completo
2. Verificar en qué fase está el proyecto revisando qué archivos existen
3. Reportar el estado actual: "Estás en Fase X, sprint Y. Lo que sigue es..."
4. NO proponer funcionalidades de fases futuras hasta completar la actual
5. **NUEVA REGLA (Evaluación de Mercado):** Cada vez que una fase alcance el 100%, realizar obligatoriamente un "Cuestionamiento de Mercado". Preguntarse qué características le faltan a esta fase en comparación con los mejores softwares del mundo, presentárselas al usuario y evaluar si agregarlas (como una Fase X.1) o descartarlas.
6. Si detecta que falta algo crítico (trigger, índices, .env), señalarlo primero

```bash
# Comandos de diagnóstico que Claude Code puede ejecutar al iniciar
ls app/models/          # ver qué modelos existen
ls app/api/             # ver qué routers existen (vacío = aún en Fase 1)
alembic current         # ver estado de las migraciones
psql -U salmonera_user -d salmonera_db -c "\dt"  # ver tablas creadas
```

---

*Skill generada para el proyecto Inventario 3D Salmonera*
*INACAP Ingeniería en Informática — Región de Los Lagos — 2026*
*Última actualización: Abril 2026*