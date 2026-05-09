# PROGRESO — Sprint 1 + Sprint 2
# Actualizado automáticamente — leer aquí si se corta la sesión

## Resultado final: 42/42 tests PASSED ✅ (Sprint 1 + Sprint 2 completos)

## Estado por tarea

### SPRINT 1
- [x] AXI-5  — python-jose 3.3.0 en requirements.txt
- [x] AXI-6  — CORS desde settings.CORS_ORIGINS
- [x] AXI-20 — .env.example + .gitignore creados
- [x] AXI-9  — Paginación COUNT(*) en containers/galpones/productos
- [x] BUG    — container.fecha_ultimo_movimiento → container.ultimo_movimiento (4 ocurrencias en movimientos.py)
- [x] AXI-7  — Migración Alembic: trigger inmutabilidad movimiento
- [x] AXI-8  — Migración Alembic: 7 índices PostgreSQL (misma migración)
- [x] AXI-10 — scripts/seed.py con datos Skretting
- [x] TEST   — tests/conftest.py (infraestructura SQLite async)
- [x] TEST   — tests/test_auth.py
- [x] TEST   — tests/test_containers.py

### SPRINT 2
- [x] AXI-13 — POST /movimientos/sync reescrito (inserta real en BD)
- [x] AXI-11 — app/services/fefo.py + GET /movimientos/fefo
- [x] AXI-12 — GET /movimientos/trazabilidad
- [x] AXI-21 — app/services/picking.py + GET /movimientos/ruta-picking
- [x] TEST   — tests/test_fefo.py
- [x] TEST   — tests/test_sync.py
- [x] TEST   — tests/test_picking.py
- [x] TEST   — tests/test_trazabilidad.py

## Cómo continuar si se cortan los tokens

```bash
cd inventario-salmonera/backend

# Verificar qué está hecho
python -m pytest tests/ -v --tb=short 2>&1 | head -60

# Si falta algún test, revisar la lista de arriba y el archivo correspondiente
# Si falta algún servicio, revisar app/services/
# Si falta la migración, revisar alembic/versions/

# Para correr los tests localmente (SQLite in-memory):
pip install pytest pytest-asyncio httpx aiosqlite
pytest tests/ -v

# Para correr contra PostgreSQL real:
# Asegurarse que .env tiene DATABASE_URL correcto
# pytest tests/ -v --db=postgres  (ver conftest.py)
```

## Archivos creados/modificados en esta sesión

### Modificados
- requirements.txt (python-jose 3.3.0, + pytest deps)
- app/core/config.py (CORS_ORIGINS)
- app/main.py (settings.CORS_ORIGINS)
- app/api/containers.py (COUNT(*), func import)
- app/api/galpones.py (COUNT(*), func import)
- app/api/productos.py (COUNT(*), func import)
- app/api/movimientos.py (bug fix ultimo_movimiento, sync real, nuevos endpoints)

### Creados
- .env.example
- .gitignore
- alembic/versions/e5f9a2b3c1d4_trigger_inmutabilidad_e_indices.py
- scripts/seed.py
- app/services/fefo.py
- app/services/picking.py
- app/services/sync.py
- tests/__init__.py
- tests/conftest.py
- tests/test_auth.py
- tests/test_containers.py
- tests/test_fefo.py
- tests/test_sync.py
- tests/test_picking.py
- tests/test_trazabilidad.py
- PROGRESO.md (este archivo)
