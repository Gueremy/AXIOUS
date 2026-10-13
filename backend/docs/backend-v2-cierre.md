# Cierre verificable del backend SalmoTrack v2

**Rama de trabajo:** `feat/backend-v2-complete` (derivada de `origin/feat/backend-v2`, commit `214dfbb`).
**Alcance:** sólo `backend/`. La aplicación v1 conserva sus rutas y pruebas; las cuentas v2 operan por `/api/v2`.

## Criterio de aceptación

El contrato backend para conectar el frontend v2 queda implementado y verificado en una base PostgreSQL de prueba migrada con Alembic. El recorrido automatizado de 21 pasos cubre dos organizaciones, usuarios, jerarquía de sitios y zonas, stock, movimientos, aprobación, reintento offline, importación, conciliación, KPIs, exportación, aislamiento y pack salmonero opcional.

| Fases del plan | Evidencia principal |
| --- | --- |
| 0A–0D | Suite v1 preservada; dominio y API v2; tenant tomado del usuario autenticado; sitios y roles con permisos configurables. |
| 1A–1C | Solicitudes y libro inmutable, saldos transaccionales, trigger PostgreSQL, bloqueo concurrente, índices de idempotencia y sincronización offline. |
| 1D–1G | Alertas programadas, importación CSV/Excel, mapeo y conciliación, dashboard, exportaciones y BI con alcance por sitio. |
| 2–2E | Módulos opcionales y feature flags, bus de eventos, pack salmonero desacoplado y picking FEFO/FIFO/LIFO configurable. |
| 3–4 | API de layout, seed demo idempotente, conectores, eventos entrantes idempotentes y webhooks firmados con cola persistente y reintentos. |

Las pruebas rápidas pasan con **141/141** casos. Las pruebas de integración PostgreSQL pasan con **4/4** casos, incluida la reproducción del recorrido global. La cadena completa de migraciones se aplicó desde una base vacía y `alembic check` no detectó diferencias entre el esquema migrado y los modelos. PostgreSQL verifica JSONB, índices, trigger, restricción de saldos sin lote y aprobación concurrente. OpenAPI actualizado: `docs/openapi-v2.json`.

## Cómo repetir la verificación

Configurar `DATABASE_URL`, `DATABASE_URL_SYNC`, `SECRET_KEY` y `ENVIRONMENT=test` con una base PostgreSQL desechable cuyo nombre incluya `axious_v2_completion_test`. Luego ejecutar desde `backend/`:

```bash
alembic upgrade head
alembic check
pytest -q tests
pytest -q tests_postgres
```

`tests_postgres` se omite si no se proporciona esa base dedicada. La prueba SQLite rápida usa la configuración y las dependencias de `tests/conftest.py`.

## Límites del cierre

El cierre acredita el **contrato de backend en entorno de prueba**, no un despliegue. No se ejecutaron conectores contra SAP, WMS u otros sistemas reales ni se entregó un webhook a un destino externo; la entrega y los reintentos se probaron con un emisor simulado. Tampoco se aplicaron migraciones sobre una base de producción ni se adaptó el frontend. Antes de operar con datos reales hace falta un ensayo de migración con una copia autorizada, configuración de secretos y endpoints externos, y pruebas de extremo a extremo con el frontend v2.

La publicación de un evento de movimiento ocurre después del commit; existe una ventana de fallo de proceso antes de encolar su webhook. La cola y los reintentos son persistentes una vez encolado el evento. Para entrega garantizada incluso frente a esa ventana se requiere integrar el encolado en la misma transacción del movimiento.
