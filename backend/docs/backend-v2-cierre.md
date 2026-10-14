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

Las pruebas rápidas pasan con **149/149** casos. Las pruebas de integración PostgreSQL pasan con **5/5** casos, incluida la reproducción del recorrido global. La cadena completa de migraciones se aplicó desde una base vacía y `alembic check` no detectó diferencias entre el esquema migrado y los modelos. PostgreSQL verifica JSONB, índices, trigger, restricción de saldos sin lote, aprobación concurrente y flujo multietapa con unidades convertidas. OpenAPI actualizado: `docs/openapi-v2.json`.

## Ampliación según los requisitos generales modulares

El backend cubre RG-01 a RG-22 y RG-26. RG-23 a RG-25 son almacenamiento y cola locales del cliente, fuera de este backend. Las diez brechas detectadas en la revisión del documento general se cerraron así:

| Requisito | Contrato backend añadido o corregido |
| --- | --- |
| RG-03 | Las actualizaciones de ítems, zonas, ubicaciones y lotes validan JSON Schema. Los atributos inválidos responden 422. |
| RG-04 | `GET/PATCH /api/v2/configuracion-operativa` mantiene unidades por organización. El motor convierte magnitudes compatibles al calcular ocupación y capacidad; rechaza pérdidas de precisión. |
| RG-05 | Las reglas se aplican sólo al sitio, zona y ubicación configurados; conciliación y movimientos evalúan límites y permisos de almacenamiento. |
| RG-06 | Umbrales 40/80 y paleta de cinco estados configurables por organización. Las alertas de inactividad, conciliación, ubicación retenida y movimientos fuera de horario se generan desde reglas configurables. |
| RG-09 | `POST /api/v2/importacion/conciliar-api` acepta filas JSON con mapeo inline o guardado y usa el mismo conciliador que CSV/Excel. |
| RG-12 | `GET /api/v2/exportaciones/{recurso}/{formato}` exporta datos operativos y vistas de BI a CSV, Excel o PDF, con página, tamaño y total explícitos. |
| RG-14 | Los tipos de movimiento admiten etapas, roles y estados finales configurables. Cada etapa queda auditada; el stock cambia sólo en la aprobación final. |
| RG-17 | El generador demo incluye presets ficticios salmonera, distribución general, retail y portuario. |
| RG-18 | Los manifiestos declaran rutas, tablas, permisos, pantallas y eventos, además de activación por organización. |
| RG-19 | Los reportes del núcleo reciben datos del módulo de importación por un proveedor registrado. La importación emite `importacion.finalizada`; movimientos emiten eventos para webhooks y alertas. |

Cuando una organización mezcla unidades, los KPIs incluyen desglose por unidad y `totales_comparables=false`; los totales escalares antiguos se conservan para los clientes existentes. El API de exportación pagina para no truncar datos silenciosamente; consulte `X-Export-Total` y recorra las páginas. Los conectores externos concretos de cámaras, GPS y ERP siguen siendo integraciones posteriores; la interfaz, el endpoint de entrada y los webhooks están disponibles para implementarlos.

El documento general menciona nueve alertas heredadas, pero `app/models/alerta.py` enumera ocho. La configuración v2 incluye las ocho identificables; hace falta definir la novena si se espera una alerta adicional.

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
