# Baseline del Backend: SalmoTrack v1 → v2
**Fecha de ejecución:** 12 de Octubre de 2026  
**Rama:** `feat/backend-v2`  
**Entorno de pruebas:** Python 3.11.9 (`backend/.venv`), pytest 8.3.5, pytest-asyncio 0.24.0, aiosqlite 0.20.0, FastAPI 0.135.3, SQLAlchemy 2.0.49

---

## 1. Resultado Real de Pruebas Automatizadas

La suite de pruebas preexistente en `backend/tests/` fue ejecutada en su totalidad con el siguiente resultado verificado:

```text
============================= 92 passed in 2.60s ==============================
```

### Desglose por módulo de prueba:
| Archivo de Prueba | Tests Aprobados | Foco de Validación |
| :--- | :---: | :--- |
| `tests/test_alertas.py` | 13 | 8 tipos de alertas, deduplicación, permisos por rol, aislamiento por sede |
| `tests/test_auth.py` | 8 | Login JWT, credenciales inválidas, usuarios inactivos, endpoints protegidos |
| `tests/test_containers.py` | 5 | Paginación `SELECT COUNT(*)`, límites y aislamiento multi-sede |
| `tests/test_dashboard.py` | 12 | KPIs (ocupación, alertas, vencimientos), Recharts BarChart/LineChart, aislamiento |
| `tests/test_fefo.py` | 6 | First Expired First Out ordenado ASC, solo disponibles y aprobados |
| `tests/test_movimientos_list.py` | 4 | Listado enriquecido, búsqueda y aislamiento de sedes |
| `tests/test_picking.py` | 12 | Algoritmo Nearest Neighbor, distancia Manhattan simétrica, preservación de lista |
| `tests/test_reportes.py` | 10 | Generación PDF/Excel, validación Ley 19.628 (sin RUT, con código de empleado) |
| `tests/test_scheduler.py` | 5 | APScheduler jobs nocturno (02:00) y periódico (30 min) |
| `tests/test_sync.py` | 5 | Endpoint offline sync, rechazo por falta de capacidad o container inexistente |
| `tests/test_trazabilidad.py` | 5 | Historial de lote, confidencialidad RUT, roles permitidos |
| `tests/test_trigger.py` | 7 | Inmutabilidad de movimientos, bloqueo de modificaciones a campos críticos |
| **Total** | **92 / 92 PASSED** | **100% de la suite actual operativa** |

---

## 2. Estado de Migraciones Alembic y Base de Datos

* **Cadena de migraciones:** 7 revisiones lineales continuas:
  `<base> -> 7011ef78763b -> 777a62cf61fb -> fbf2a21dfc87 -> d367941070ea -> e5f9a2b3c1d4 -> f1a2b3c4d5e6 -> a1b2c3d4e5f6 (head)`
* **Head actual:** `a1b2c3d4e5f6_trigger_inmutabilidad_selectivo.py`.
* **Verificación de DDL Transaccional:** Se ejecutó `alembic upgrade head --sql` generando el DDL completo desde una base vacía hacia el estado actual de forma limpia y sin errores de sintaxis.

---

## 3. Verificación de Arranque y Health Check

FastAPI inicia correctamente y el endpoint `/health` responde código `200 OK`:
```json
{
  "status": "ok",
  "environment": "development",
  "version": "3.0.0",
  "websocket_connections": 0,
  "scheduler_running": false,
  "websocket_url": "ws://localhost:8000/ws/alertas/{id_sede}?token={jwt}"
}
```

* **Snapshot OpenAPI v1 generado en:** `backend/docs/openapi-v1.json` (127 KB, 47 endpoints REST documentados).

---

## 4. Inventario de Dependencias del Dominio Legacy

Se identificaron **1.087 referencias** a entidades y conceptos específicos de salmonera en el código fuente de `app/`:

| Concepto / Entidad | Conteo Referencias | Archivos Clave con Dependencia |
| :--- | :---: | :--- |
| `Container` | 388 | `app/models/container.py`, `app/api/containers.py`, `app/api/movimientos.py`, `app/services/alertas.py`, `app/services/fefo.py`, `app/services/picking.py` |
| `Sede` / `id_sede` | 380 | `app/models/sede.py`, `app/models/usuario.py`, `app/api/sedes.py`, `app/api/movimientos.py`, `app/api/dashboard.py`, `app/websockets.py` |
| `Galpon` / `id_galpon` | 219 | `app/models/galpon.py`, `app/models/usuario.py`, `app/api/galpones.py`, `app/api/dashboard.py` |
| `Producto` | 112 | `app/models/producto.py`, `app/api/productos.py`, `app/api/movimientos.py`, `app/services/fefo.py` |
| Campos SERNAPESCA / SAG | 40 | `app/models/movimiento.py`, `app/schemas/movimiento.py`, `app/api/movimientos.py`, `app/services/reportes.py` |
| Umbrales fijos (40% / 80%) | 82 | `app/models/container.py`, `app/services/alertas.py`, `app/api/dashboard.py` |

---

## 5. Riesgos Identificados y Estrategia de Mitigación

1. **Riesgo de Regresión durante el Refactor:**
   * *Mitigación:* Coexistencia temporal de esquemas. No se eliminarán los modelos v1 de inmediato; se incorporará el nuevo dominio genérico bajo `app/models/v2/` y `/api/v2/`, manteniendo los 92 tests actuales ejecutándose en cada fase.
2. **Dependencia Fuerte de SQLite en Tests vs Capacidades PostgreSQL:**
   * *Mitigación:* Se mantendrá SQLite in-memory para ejecuciones de desarrollo ultrarrápidas, pero las pruebas de Fase 0B y 1A (JSONB schemas, CHECKs y triggers) contarán con pruebas que validan PostgreSQL o mocks adecuados de constraints.
3. **Preservación de Datos:**
   * No existen volcados ni bases de datos de producción con datos reales en el repositorio. Los datos existentes corresponden a fixtures sintéticos generados por `scripts/seed.py`. Se creará un seed demo v2 independiente con 2 organizaciones genéricas.
