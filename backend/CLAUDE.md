# 🐟 CLAUDE.md — Estado y Tareas del Proyecto
# Sistema de Inventario 3D Salmonera — AXIOUS
# Proyecto: Gueremy Barrientos · Bastián Riffo — INACAP 2026
# ⚠️ Este archivo SE ACTUALIZA cada sprint — refleja el estado actual

---

## ⚡ INSTRUCCIÓN AL INICIAR SESIÓN

Claude Code debe hacer esto EN ORDEN al arrancar cualquier sesión:

```bash
# 1. Leer GUIDELINES.md (buenas prácticas, stack, patrones)
# 2. Leer este CLAUDE.md (estado actual y tareas pendientes)
# 3. Verificar estado real del proyecto:
ls app/models/
ls app/api/
ls app/services/
alembic current
pip show python-jose | grep Version  # debe ser 3.3.0
```

4. Reportar exactamente: **"Estás en Sprint X. La próxima tarea es AXI-Y: [descripción]"**
5. NO proponer funcionalidades de sprints futuros hasta completar el actual
6. Si detecta deuda técnica crítica (CVE activo, trigger faltante, CORS hardcodeado) → señalarla PRIMERO antes de cualquier otra cosa

---

## Estado General — Mayo 2026

```
Progreso global del backend: 100% ✅ COMPLETO

✅ COMPLETADO (no tocar):
   Fase 1 — Fundamentos    : modelos, BD PostgreSQL, Alembic, entorno virtual
   Fase 2 — Auth JWT       : login, refresh token, roles, rate limiting, bcrypt
   Fase 3 — CRUD Core      : sedes, galpones, containers, productos, usuarios, QR, CSV
   Fase 4 — Movimientos    : flujo completo, aprobación, rechazo, SAG/SERNAPESCA
   S1 — Hotfix & Fundamentos : python-jose 3.3.0, CORS env, paginación, trigger, indices, seed
   S2 — FEFO + Trazabilidad  : sync real, FEFO, trazabilidad lotes, ruta picking
   S3 — Motor Alertas + WS   : 8 tipos alerta, WebSockets, APScheduler, CRUD alertas
   S4 — Dashboard + Reportes : KPIs, ocupación por galpón, evolución, PDF, Excel, SERNAPESCA

⏳ PENDIENTE: nada — backend 100% completo
```

---

## Estructura de Carpetas — Estado Actual

```
backend/
├── app/
│   ├── api/
│   │   ├── auth.py         ✅ completo
│   │   ├── sedes.py        ✅ completo
│   │   ├── galpones.py     ✅ completo
│   │   ├── containers.py   ✅ completo
│   │   ├── productos.py    ✅ completo
│   │   ├── usuarios.py     ✅ completo
│   │   ├── movimientos.py  ✅ completo (sync pendiente — AXI-13)
│   │   ├── alertas.py      ✅ completo (AXI-17)
│   │   ├── dashboard.py    ✅ completo — KPIs, ocupación, evolución (AXI-18)
│   │   └── reportes.py     ✅ completo — PDF, Excel, SERNAPESCA (AXI-19)
│   ├── models/             ✅ 9 modelos completos
│   ├── schemas/            ✅ completos (alerta.py + dashboard.py)
│   ├── services/
│   │   ├── alertas.py      ✅ completo — 8 tipos + deduplicación + batch (AXI-14)
│   │   ├── fefo.py         ✅ completo (AXI-11)
│   │   ├── picking.py      ✅ completo (AXI-21)
│   │   ├── sync.py         ✅ completo — inserta real en BD (AXI-13)
│   │   └── reportes.py     ✅ completo — PDF/Excel/SERNAPESCA (AXI-19)
│   ├── core/
│   │   ├── config.py       ✅ CORS desde env
│   │   ├── security.py     ✅
│   │   ├── audit.py        ✅
│   │   └── database.py     ✅
│   ├── websockets.py       ✅ completo — ConnectionManager (AXI-15)
│   ├── scheduler.py        ✅ completo — 2 jobs APScheduler (AXI-16)
│   └── main.py             ✅ v3.0.0 — lifespan + WS endpoint
├── alembic/versions/       ✅ 5 migraciones (trigger + índices incluidos)
├── scripts/seed.py         ✅ completo (AXI-10)
├── .env                    ✅ existe — NUNCA commitear
├── .env.example            ✅ completo (AXI-20)
├── requirements.txt        ✅ python-jose==3.3.0 + APScheduler==3.10.4
├── CLAUDE.md               ✅ este archivo
└── GUIDELINES.md           ✅ buenas prácticas permanentes
```

---

## 📋 TAREAS PENDIENTES — Orden Obligatorio

> Seguimiento en Linear:
> https://linear.app/axious/project/axious-backend-sistema-inventario-3d-14d0cea7dea3
>
> Flujo de cada tarea:
> Linear: Todo → In Progress → In Review → Done
> Git: git checkout -b axi-{N}-{descripcion} → PR → merge a develop

---

### ══════════════════════════════════════════
### SPRINT 1 — Hotfix & Fundamentos Sólidos
### Semana: 7–14 Mayo 2026 | Linear: TODO
### ══════════════════════════════════════════

---

#### AXI-5 🔴 CRÍTICO — Bajar python-jose a 3.3.0
**Responsable: Gueremy | Depende de: nada | Rama: axi-5-python-jose**

```bash
# 1. Editar requirements.txt:
#    python-jose==3.5.0  →  python-jose==3.3.0

# 2. Reinstalar y verificar:
pip install -r requirements.txt
pip-audit
# Expected: No known vulnerabilities found

# 3. Correr tests de auth:
pytest tests/test_auth.py -v
# Expected: todos pasan
```

**Done cuando:** pip-audit sin vulnerabilidades críticas y todos los tests de auth pasan.

---

#### AXI-6 🔴 CRÍTICO — CORS desde variable de entorno
**Responsable: Gueremy | Depende de: nada | Rama: axi-6-cors-env**

```python
# app/core/config.py — agregar:
CORS_ORIGINS: list[str] = Field(default=["http://localhost:5173"])

# app/main.py — reemplazar la lista hardcodeada:
# ANTES: allow_origins=["http://localhost:5173", "http://localhost:3000"]
# DESPUÉS:
allow_origins=settings.CORS_ORIGINS
```

**Done cuando:** curl con Origin de producción retorna el header CORS correcto.

---

#### AXI-20 — Crear .env.example documentado
**Responsable: Gueremy | Depende de: AXI-6 | Rama: axi-20-env-example**

```env
# Crear .env.example en raíz — ver contenido completo en GUIDELINES.md
# Verificar que .env está en .gitignore y .env.example NO está en .gitignore
```

**Done cuando:** clonar el repo en máquina nueva → copiar .env.example → servidor levanta sin errores.

---

#### AXI-7 🔴 CRÍTICO — Trigger SQL inmutabilidad en movimiento
**Responsable: Bastián | Depende de: nada | Rama: axi-7-trigger-inmutabilidad**

```bash
# Crear nueva migración:
alembic revision --autogenerate -m "trigger_inmutabilidad_y_indices"

# En upgrade() del archivo generado:
```
```python
def upgrade():
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_movimiento_update()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'Los movimientos son inmutables (SERNAPESCA).
                             Usar tipo=correccion para rectificar.';
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_movimiento_immutable
        BEFORE UPDATE OR DELETE ON movimiento
        FOR EACH ROW EXECUTE FUNCTION prevent_movimiento_update();
    """)

def downgrade():
    op.execute("""
        DROP TRIGGER IF EXISTS trg_movimiento_immutable ON movimiento;
        DROP FUNCTION IF EXISTS prevent_movimiento_update();
    """)
```

**Done cuando:** `UPDATE movimiento SET cantidad=1 WHERE...` lanza excepción en psql.

---

#### AXI-8 — Índices PostgreSQL completos
**Responsable: Bastián | Depende de: AXI-7 (misma migración) | Rama: axi-7-trigger-inmutabilidad**

```python
# Agregar en la misma migración del trigger:
def upgrade():
    # ... trigger de arriba ...
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_movimiento_numero_lote
            ON movimiento (numero_lote);
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_movimiento_lote_gin
            ON movimiento USING gin(to_tsvector('spanish', numero_lote));
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_movimiento_fecha_vencimiento
            ON movimiento (fecha_vencimiento ASC) WHERE estado = 'aprobado';
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_movimiento_container_fecha
            ON movimiento (id_container, fecha_hora DESC);
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_container_galpon_estado
            ON container (id_galpon, estado);
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_movimiento_pendiente
            ON movimiento (estado, fecha_hora DESC) WHERE estado = 'pendiente';
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_alerta_activa
            ON alerta (id_container, estado) WHERE estado = 'activa';
    """)
```

**Done cuando:** `\di` en psql muestra los 7 índices nuevos.

---

#### AXI-9 — Paginación con SELECT COUNT(*) real
**Responsable: Gueremy | Depende de: nada | Rama: axi-9-paginacion-count**

```python
# Corregir en: app/api/containers.py, galpones.py, productos.py

# ❌ ANTES (carga todo en RAM):
items = await db.execute(select(Container))
total = len(items.scalars().all())

# ✅ DESPUÉS (eficiente):
from sqlalchemy import func
count_stmt = select(func.count()).select_from(Container).where(filtros)
total = await db.scalar(count_stmt)
items_stmt = select(Container).where(filtros).offset(skip).limit(limit)
items = (await db.execute(items_stmt)).scalars().all()
```

**Done cuando:** GET /containers?limit=5 retorna total correcto sin traer todos los registros.

---

#### AXI-10 — Script seed.py con datos reales Skretting
**Responsable: Bastián | Depende de: AXI-8 | Rama: axi-10-seed**

```python
# Crear scripts/seed.py con:
# - 1 empresa: Skretting Chile Ltda.
# - 4 sedes: Pontón Chiloé, Pontón Aysén, Planta Puerto Montt, Bodega Insumos
# - 3 galpones por sede = 12 galpones
# - 15 containers por galpón = 180 containers
# - 5 productos por categoría = 25 productos
# - 2 usuarios por rol = 10 usuarios
# - 50 movimientos con campos SERNAPESCA variados

# Output esperado:
# python scripts/seed.py
# ✅ Empresa creada: Skretting Chile Ltda.
# ✅ Sedes creadas: 4
# ✅ Galpones creados: 12
# ✅ Containers creados: 180
# ✅ Usuarios creados: 10
# ✅ Movimientos creados: 50
```

**Done cuando:** seed.py corre sin errores y pgAdmin muestra los datos.

---

**Tests de cierre S1:**
```bash
pip-audit                           # 0 vulnerabilidades críticas
pytest tests/test_auth.py -v        # pasan con jose 3.3.0
pytest tests/test_containers.py -v  # paginación correcta
python scripts/seed.py              # output limpio
# psql: UPDATE movimiento SET cantidad=1 WHERE id=... → debe fallar
```

---

### ══════════════════════════════════════════
### SPRINT 2 — FEFO + Trazabilidad + Sync Real
### Semana: 15–21 Mayo 2026 | Linear: BACKLOG
### Mover a TODO al inicio de la semana 2
### Requisito: todos los AXI de S1 en Done
### ══════════════════════════════════════════

---

#### AXI-11 — GET /movimientos/fefo
**Responsable: Gueremy | Depende de: AXI-8**

```python
# Crear app/services/fefo.py
# Endpoint: GET /movimientos/fefo?id_producto=X&id_sede=Y
# Retorna containers con ese producto ordenados por fecha_vencimiento ASC
# Ver implementación completa en GUIDELINES.md → sección Algoritmos
```

---

#### AXI-12 — GET /movimientos/trazabilidad
**Responsable: Bastián | Depende de: AXI-8**

```python
# Endpoint: GET /movimientos/trazabilidad?numero_lote=X
# Historial completo del lote — debe responder en < 2 segundos
# Usar índice GIN creado en AXI-8
# Response incluye: fecha, tipo, container, galpon, sede, codigo_empleado (NUNCA rut)
```

---

#### AXI-13 🔴 CRÍTICO — Reescribir POST /movimientos/sync
**Responsable: Bastián | Depende de: AXI-10**

```python
# Reescribir app/services/sync.py — actualmente NO inserta en BD
# Schema entrada: lista de MovimientoOffline con uuid_local (ID de Dexie.js)
# Lógica: Last-Write-Wins con validación de capacidad
# Si excede capacidad → accion: "rechazar" con motivo
# Si OK → insertar Movimiento con origen="offline_sync"
# Ver implementación completa en GUIDELINES.md → sección Algoritmos
```

---

#### AXI-21 — GET /movimientos/ruta-picking
**Responsable: Gueremy | Depende de: AXI-11**

```python
# Crear app/services/picking.py
# Endpoint: GET /movimientos/ruta-picking?containers=id1,id2,id3
# Algoritmo Nearest Neighbor con distancia Manhattan
# Ver implementación completa en GUIDELINES.md → sección Algoritmos
```

---

**Tests de cierre S2:**
```bash
pytest tests/test_fefo.py -v         # orden ASC por fecha_vencimiento
pytest tests/test_trazabilidad.py -v # < 2 segundos con seed completo
pytest tests/test_sync.py -v         # inserción real + conflictos correctos
pytest tests/test_picking.py -v      # distancia menor que orden aleatorio
```

---

### ══════════════════════════════════════════
### SPRINT 3 — Motor Alertas + WebSockets
### Semana: 22–28 Mayo 2026 | Linear: BACKLOG
### Requisito: S2 completo
### ══════════════════════════════════════════

---

#### AXI-14 🔴 — evaluar_alertas() con 8 tipos
**Responsable: Gueremy | Depende de: S2 completo**

```python
# Reemplazar el pass actual en app/services/alertas.py
# Implementar los 8 tipos del ALERTAS_CONFIG (ver GUIDELINES.md)
# Integrar en PATCH /movimientos/{id}/aprobar después de actualizar ocupacion_actual
```

---

#### AXI-15 — WebSocket /ws/alertas/{id_sede}
**Responsable: Gueremy | Depende de: AXI-14**

```python
# Crear app/websockets.py con ConnectionManager
# Endpoint WS en main.py: /ws/alertas/{id_sede}
# Al crear alerta → manager.broadcast(id_sede, {...})
# Ver implementación completa en GUIDELINES.md → sección WebSockets
```

---

#### AXI-16 — APScheduler 3 jobs
**Responsable: Bastián | Depende de: AXI-14**

```python
# Crear app/scheduler.py
# Job 1: CronTrigger(hour=2) → evaluar vencimientos y sin movimiento
# Job 2: IntervalTrigger(minutes=30) → stock mínimo y discrepancias
# Integrar en lifespan de main.py
# ⚠️ Solo funciona correctamente con --workers 1
```

---

#### AXI-17 — Router alertas.py
**Responsable: Bastián | Depende de: AXI-14**

```python
# Crear app/api/alertas.py
# GET  /alertas/activas?id_sede=X
# GET  /alertas/historial?id_sede=X
# PATCH /alertas/{id}/revisar
# PATCH /alertas/{id}/resolver
# Filtrar SIEMPRE por id_sede del usuario autenticado
```

---

**Tests de cierre S3:**
```bash
pytest tests/test_alertas.py -v      # 8 tipos, aislamiento sede
pytest tests/test_scheduler.py -v    # jobs registrados
# wscat -c ws://localhost:8000/ws/alertas/{id}
# → aprobar movimiento → alerta llega en tiempo real
```

---

### ══════════════════════════════════════════
### SPRINT 4 — Dashboard KPIs + PDF/Excel
### Semana: 29 Mayo – 4 Junio 2026 | Linear: BACKLOG
### Requisito: S3 completo
### Este sprint cierra el backend al 100% ✅
### ══════════════════════════════════════════

---

#### AXI-18 — Dashboard KPIs
**Responsable: Bastián | Depende de: S3 completo**

```python
# Crear app/api/dashboard.py
# GET /dashboard/kpis?id_sede=X
# → { ocupacion_global, alertas_activas, movimientos_hoy, proximo_vencimiento }
# GET /dashboard/ocupacion-por-galpon?id_sede=X
# → [{ name, ocup, estado }]  ← formato Recharts BarChart
# GET /dashboard/evolucion?id_sede=X&dias=30
# → [{ fecha, movimientos }]  ← formato Recharts LineChart
# Filtrar por id_sede del token — 403 si intenta ver otra sede
```

---

#### AXI-19 — Exportación PDF + Excel + SERNAPESCA
**Responsable: Gueremy | Depende de: S3 completo**

```python
# Crear app/services/reportes.py
# GET /reportes/movimientos/pdf  → reportlab, logo Skretting, tabla SERNAPESCA
# GET /reportes/movimientos/excel → openpyxl, columnas auditables, autoajuste
# GET /reportes/sernapesca       → formato específico normativa
# ⚠️ NUNCA incluir RUT en ningún reporte (Ley 19.628)
```

---

**Tests de cierre S4 (= backend 100%):**
```bash
pytest tests/test_dashboard.py -v    # KPIs correctos, aislamiento sede
pytest tests/test_reportes.py -v     # PDF >5KB, Excel válido y abrible
pytest --tb=short                    # suite completa sin errores
```

---

## Reglas de trabajo en equipo

```
Ramas Git:
  main     → producción, solo merge por PR aprobado
  develop  → integración, todos los PRs van aquí
  axi-{N}-{descripcion} → una rama por issue

PRs:
  Nombre: [AXI-5] Bajar python-jose a 3.3.0
  Nadie mergea su propio PR — siempre lo revisa el otro
  Merge a develop → mover issue a Done en Linear

Máximo 2 issues en In Progress al mismo tiempo (1 por persona)
Si un issue está bloqueado → marcarlo Blocked en Linear + avisar
Al terminar cada sprint → revisión de 15 min antes del siguiente
```

---

*CLAUDE.md — Se actualiza al iniciar cada nuevo sprint*
*Última actualización: Mayo 2026 — Sprint 4 completado — BACKEND 100% ✅*
*Tests: 82/82 PASSED (S1+S2+S3+S4)*
*Seguimiento: https://linear.app/axious/project/axious-backend-sistema-inventario-3d-14d0cea7dea3*
*Buenas prácticas permanentes: ver GUIDELINES.md*
