# 🐟 GUIDELINES — Sistema de Inventario 3D Salmonera
# Buenas prácticas, patrones y estándares del proyecto
# Proyecto: Gueremy Barrientos · Bastián Riffo — INACAP 2026
# ⚠️ Este archivo NO cambia entre sprints — es referencia permanente

---

## Contexto del Proyecto

Sistema web de gestión de inventario con visualización 3D interactiva para
**Skretting**, empresa salmonera de la Región de Los Lagos, Chile.

- **Cliente real**: Skretting Chile Ltda. (empresa salmonera colaboradora)
- **Contacto cliente**: Bastián Riffo (contacto directo en Skretting)
- **Problema**: Inventario gestionado en Excel sin visibilidad espacial ni trazabilidad. +1.000 hrs/año perdidas por sede.
- **Solución**: App web 3D multi-sede, 5 roles, offline en pontones, cumplimiento SERNAPESCA automático y capa BI integrada.
- **Institución**: INACAP Puerto Montt — Ingeniería en Informática — Proyecto de Título 2026

---

## Stack Tecnológico (NO cambiar sin consultar)

```
Backend  : FastAPI 0.110+ · Python 3.11+ · SQLAlchemy 2.x async · Alembic
Auth     : python-jose==3.3.0 (JWT HS256) · passlib[bcrypt] (cost=12)
           ⚠️  FIJAR en 3.3.0 — NO actualizar (CVE-2024-33663 en ECDSA)
BD       : PostgreSQL 15+ · asyncpg==0.31.0 (driver async)
           psycopg2-binary SOLO para alembic/env.py — nunca en código async
WS       : FastAPI WebSockets nativo (sin Django Channels ni Redis)
Scheduler: APScheduler 3.x — SIEMPRE --workers 1 (jobs se duplican con más)
Reportes : reportlab (PDF) · openpyxl (Excel)
Deploy   : DigitalOcean Droplet São Paulo · Nginx · Gunicorn (1 worker) + Uvicorn
Frontend : React Three Fiber · TanStack Query · Dexie.js (offline PWA) · Zustand
           SheetJS xlsx==0.18.5 exacto — NO actualizar (versiones > 0.18.5 son de pago)
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
movimiento    → INMUTABLE (trigger PostgreSQL — nunca UPDATE ni DELETE)
alerta        → 8 tipos, 3 severidades
log_auditoria → toda acción crítica queda registrada
```

### Estados del Container (sistema de 5 colores)
```
disponible    → verde   (0–40% ocupación)
medio         → amarillo (41–79%)
critico       → rojo    (80–100%)
mantenimiento → gris    (manual)
cuarentena    → morado  (SERNAPESCA o calidad)
```

---

## ⚠️ REGLAS CRÍTICAS — Nunca violar

### 1. LEY 19.628 — Protección de datos personales
```python
# El RUT NUNCA debe aparecer en:
#   - Ningún response schema de la API
#   - Logs de Nginx o de la aplicación
#   - Reportes externos (SERNAPESCA, auditores)
#   - Mensajes de error
# Usar SIEMPRE: codigo_empleado en reportes externos

# ✅ CORRECTO
class UsuarioRead(BaseModel):
    id: UUID
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
# Para corregir un error → movimiento tipo "correccion"
# con id_movimiento_original apuntando al registro erróneo

# ✅ CORRECTO
nuevo = Movimiento(
    tipo="correccion",
    id_movimiento_original="uuid-del-movimiento-erróneo",
    observaciones="Corrección: cantidad era 50kg, no 500kg"
)

# ❌ INCORRECTO — el trigger lanzará excepción PostgreSQL
await db.execute(update(Movimiento).where(Movimiento.id == id))
```

### 3. Jefe de bodega NO aprueba sus propios movimientos (OWASP A04)
```python
@router.patch("/{id}/aprobar")
async def aprobar_movimiento(
    id: UUID,
    current_user: Usuario = Depends(require_role(["jefe_bodega", "super_admin"]))
):
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

# Validar con @field_validator en el schema Pydantic
```

### 5. Separación de productos (alimento ≠ químico)
```python
INCOMPATIBLE = {
    "alimento": ["quimico"],
    "quimico":  ["alimento", "veterinario"],
}

def validar_compatibilidad(tipo_producto: str, tipo_permitido_container: str):
    if tipo_producto in INCOMPATIBLE.get(tipo_permitido_container, []):
        raise HTTPException(400,
            f"El container no permite {tipo_producto} junto a {tipo_permitido_container}")
```

### 6. Aislamiento multi-sede (siempre)
```python
# TODOS los queries filtran por id_sede del usuario autenticado
# NUNCA devolver datos de otra sede, aunque el id sea correcto

stmt = select(Container).where(
    Container.id == container_id,
    Container.galpon.has(Galpon.id_sede == current_user.id_sede)  # AISLAMIENTO
)
```

---

## Algoritmos del Proyecto

### FEFO — First Expired, First Out (app/services/fefo.py)
```python
# Ordenar por fecha_vencimiento ASC — el que vence antes sale primero
# Objetivo: reducir mermas del 1.5% actual a < 1%

async def sugerir_container_fefo(db, id_producto, id_sede):
    stmt = (
        select(
            Container.id, Container.codigo,
            Movimiento.fecha_vencimiento, Movimiento.numero_lote
        )
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
# Nearest Neighbor — Complejidad O(n²), aceptable para n < 50 containers/pedido

def distancia_manhattan(a: tuple, b: tuple) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])

def optimizar_ruta(containers: list[dict], inicio=(0, 0)) -> list[dict]:
    pendientes = containers.copy()
    ruta, pos, distancia_total = [], inicio, 0
    while pendientes:
        mas_cercano = min(
            pendientes,
            key=lambda c: distancia_manhattan(pos, (c["fila"], c["col"]))
        )
        dist = distancia_manhattan(pos, (mas_cercano["fila"], mas_cercano["col"]))
        mas_cercano["distancia_desde_anterior"] = dist
        distancia_total += dist
        ruta.append(mas_cercano)
        pos = (mas_cercano["fila"], mas_cercano["col"])
        pendientes.remove(mas_cercano)
    return {"ruta_optimizada": ruta, "distancia_total": distancia_total}
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
# /etc/nginx/sites-available/axious
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "DENY" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;

# Deshabilitar Swagger en producción
location /docs         { return 404; }
location /redoc        { return 404; }
location /openapi.json { return 404; }
```

### Manejo seguro de secretos
```python
# NUNCA hardcodear credenciales en el código
class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str        # mínimo 32 caracteres aleatorios
    ENVIRONMENT: str = "development"
    CORS_ORIGINS: list[str] = Field(default=["http://localhost:5173"])

    model_config = ConfigDict(env_file=".env")

# Generar SECRET_KEY seguro:
# python -c "import secrets; print(secrets.token_hex(32))"
```

---

## Optimización de Base de Datos

### Índices obligatorios (migración Alembic — AXI-8)
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

# ❌ INCORRECTO — N+1 queries (1 extra por cada container)
containers = await db.execute(select(Container))
for c in containers.scalars():
    print(c.galpon.nombre)  # lazy load silencioso
```

### Proyecciones mínimas para render 3D
```python
# Solo los 8 campos que necesita React Three Fiber
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

### Paginación eficiente (nunca len() sobre lista)
```python
# ✅ CORRECTO
from sqlalchemy import func

count_stmt = select(func.count()).select_from(Container).where(filtros)
total = await db.scalar(count_stmt)

items_stmt = select(Container).where(filtros).offset(skip).limit(limit)
items = (await db.execute(items_stmt)).scalars().all()

# ❌ INCORRECTO — carga todos los registros en RAM
items = await db.execute(select(Container))
total = len(items.scalars().all())
```

### Caché TTL por tipo de dato (TanStack Query)
```python
CACHE_TTL = {
    "sedes_lista":            30 * 60,  # 30 minutos
    "galpones_por_sede":      15 * 60,  # 15 minutos
    "containers_estado":      30,        # 30 segundos
    "alertas_activas":        10,        # 10 segundos
    "movimientos_pendientes": 15,        # 15 segundos
    # Alertas en tiempo real → WebSockets (no polling)
}
```

---

## Manejo de Carga del Servidor

### Configuración Gunicorn para producción
```bash
# Para 50 usuarios activos en Droplet 2vCPU/4GB:
gunicorn app.main:app \
  --workers 1 \
  --worker-class uvicorn.workers.UvicornWorker \
  --worker-connections 100 \
  --timeout 60 \
  --keepalive 5 \
  --bind 0.0.0.0:8000

# ⚠️ SIEMPRE workers=1 por APScheduler
# Si en el futuro se necesitan más workers:
#   Solución: solo el worker con os.getpid() == os.getppid()+1 ejecuta el scheduler
```

### Connection Pool de PostgreSQL
```python
# Para 50 usuarios activos con 1 worker:
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=10,        # conexiones permanentes
    max_overflow=20,     # conexiones extra bajo pico
    pool_timeout=30,     # segundos antes de error por falta de conexión
    pool_recycle=1800,   # reciclar conexiones cada 30 min
    echo=False,          # SIEMPRE False en producción
)
```

### WebSockets — ConnectionManager
```python
class ConnectionManager:
    def __init__(self):
        self.connections: dict[str, list[WebSocket]] = {}

    async def connect(self, ws: WebSocket, id_sede: str):
        await ws.accept()
        self.connections.setdefault(id_sede, []).append(ws)

    def disconnect(self, ws: WebSocket, id_sede: str):
        if ws in self.connections.get(id_sede, []):
            self.connections[id_sede].remove(ws)

    async def broadcast_sede(self, id_sede: str, mensaje: dict):
        muertos = []
        for ws in self.connections.get(id_sede, []):
            try:
                await ws.send_json(mensaje)
            except Exception:
                muertos.append(ws)
        for ws in muertos:
            self.disconnect(ws, id_sede)
```

### Escalado por cantidad de clientes
```
1 cliente  (Skretting, ~50 usuarios):
  → Droplet $24/mes (2vCPU, 4GB) · 1 worker · pool_size=10

3 clientes (~150 usuarios):
  → Droplet $48/mes (4vCPU, 8GB) · workers según CPU · pool_size=20
  → Separar PostgreSQL a DO Managed Database ($15/mes extra)
  → Mover APScheduler a proceso separado (celery beat o proceso standalone)

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
    "capacidad_critica":        {"umbral_pct": 80,  "severidad": "critica"},
    "vencimiento_30_dias":      {"dias": 30,         "severidad": "aviso"},
    "vencimiento_7_dias":       {"dias": 7,          "severidad": "critica"},
    "stock_minimo":             {},                   # comparar con producto.stock_minimo
    "movimiento_fuera_horario": {"hora_ini": 6, "hora_fin": 22},
    "discrepancia_inventario":  {"umbral_pct": 5,   "severidad": "aviso"},
    "sin_movimiento_30_dias":   {"dias": 30,         "severidad": "informativa"},
    "cuarentena_activa":        {},                   # container.estado == "cuarentena"
}

# APScheduler jobs:
# - Cada noche 02:00 (America/Santiago): vencimientos y sin movimiento
# - Cada 30 min: stock mínimo y discrepancias
# - Inmediato post-aprobación: capacidad y horario
```

---

## Schemas Pydantic — Convenciones

```python
# Separar siempre en 3 schemas por entidad
class ContainerCreate(BaseModel):
    # POST — solo campos que envía el cliente
    ...

class ContainerRead(BaseModel):
    # GET — lo que devuelve la API
    model_config = ConfigDict(from_attributes=True)
    # NUNCA incluir rut, password_hash ni datos sensibles

class ContainerUpdate(BaseModel):
    # PATCH — todos los campos opcionales (Optional[...] = None)
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

## Errores Comunes — Evitar

```python
# ❌ python-jose > 3.3.0 → CVE-2024-33663
# ✅ fijar python-jose==3.3.0 y nunca actualizar

# ❌ lazy="dynamic" con async SQLAlchemy → error en runtime
# ✅ lazy="raise" en modelos + selectinload explícito en queries

# ❌ asyncpg + psycopg2 mezclados en código async
# ✅ asyncpg para FastAPI, psycopg2-binary SOLO para alembic/env.py

# ❌ APScheduler con --workers > 1 → jobs se ejecutan N veces
# ✅ SIEMPRE --workers 1

# ❌ echo=True en producción → logs enormes, disco lleno
# ✅ echo=settings.ENVIRONMENT == "development"

# ❌ Swagger en producción → exposición de la API
# ✅ FastAPI(docs_url=None, redoc_url=None) si ENVIRONMENT == "production"

# ❌ len() en paginación → carga todo en RAM
# ✅ SELECT COUNT(*) con func.count()

# ❌ RUT en cualquier response, log o reporte externo
# ✅ codigo_empleado siempre

# ❌ SheetJS > 0.18.5 en frontend → versión de pago
# ✅ xlsx==0.18.5 exacto en package.json

# ❌ CORS hardcodeado en main.py
# ✅ settings.CORS_ORIGINS desde .env
```

---

## Variables de Entorno (.env.example)

```env
# ── Base de datos ──────────────────────────────────────────────────────
DATABASE_URL=postgresql+asyncpg://salmonera_user:PASSWORD@localhost:5432/axious_db
DATABASE_URL_SYNC=postgresql+psycopg2://salmonera_user:PASSWORD@localhost:5432/axious_db

# ── Seguridad ──────────────────────────────────────────────────────────
# Generar con: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=CAMBIAR_POR_32_CARACTERES_ALEATORIOS
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=7

# ── CORS ───────────────────────────────────────────────────────────────
CORS_ORIGINS=["http://localhost:5173","https://salmonwise.vercel.app"]

# ── Entorno ────────────────────────────────────────────────────────────
ENVIRONMENT=development
# Opciones: development | production
# En production: Swagger deshabilitado, echo=False, logs reducidos

# ── Servidor ───────────────────────────────────────────────────────────
HOST=0.0.0.0
PORT=8000
WORKERS=1
# ⚠️ Mantener WORKERS=1 siempre — APScheduler se duplica con más workers

# ── Multi-tenant (fase futura) ─────────────────────────────────────────
TENANT_ID=skretting
```

---

## Checklist antes de cada commit

- [ ] RUT no aparece en ningún response schema ni en logs
- [ ] Todos los endpoints nuevos tienen `Depends(require_role(...))`
- [ ] Queries usan selectinload (sin lazy loading accidental)
- [ ] Campos SERNAPESCA validados en entradas de proveedor
- [ ] Sin credenciales hardcodeadas en el código
- [ ] echo=False si es código de producción
- [ ] Tests escritos para el endpoint nuevo
- [ ] Issue movido a Done en Linear

---

## Regla de Evaluación de Mercado

Cada vez que un sprint alcance el 100%, Claude Code debe obligatoriamente:

1. Preguntarse qué características tiene este módulo en los mejores softwares del mundo (SAP, Oracle WMS, Fishbowl)
2. Presentar las diferencias al equipo
3. Evaluar si agregarlas como un sprint X.1 o descartarlas
4. Solo entonces pasar al siguiente sprint

---

*GUIDELINES.md — Referencia permanente del proyecto*
*NO actualizar entre sprints — solo cuando cambie el stack o las reglas*
*INACAP Puerto Montt — Ingeniería en Informática — 2026*
