# Estado de implementación SalmoTrack

Actualizado el 8 de noviembre de 2026 (America/Santiago). El estado anterior había quedado desactualizado respecto del código local.

## Base y alcance

- Plan: `C:\Users\bravo\Downloads\PLAN.md`.
- Frontend: `feat/frontend-v2-integration-fixes`, HEAD `832273a7df8e405b04cb21b5e81be5f1b3cd0203`.
- Backend: `feat/backend-v2-complete`, HEAD `1a16a0594de196e760d238f3c2ae373135f99b3c`.
- Dos repositorios independientes en `frontend/` y `backend/`. La carpeta superior no es un repositorio Git.
- Se crearon y publicaron ramas `v3` en ambos repositorios, conservando los cambios anteriores. Frontend publicado: `b628022`; backend: `50f0c56`. CI frontend/backend e integración de navegador pasan en GitHub.
- Render conectado a `bravooreste's workspace`. El usuario aprobó el plan del Blueprint `SalmoTrack v3` (`exs-dboeitajnfac73elp0f0`); se crearon frontend, API y PostgreSQL nuevos gratuitos, sin modificar los servicios antiguos.
- Web: `https://salmotrack-v3-qq8r.onrender.com`. API: `https://salmotrack-v3-api-qq8r.onrender.com`. Migraciones aplicadas hasta `g1h2i3j4k5l6`; API responde 3.0.0 en producción, CORS correcto y endpoints protegidos responden 401 sin sesión.
- Base nueva sin usuarios ni datos previos. Falta provisionar la primera organización/cuenta administradora. PostgreSQL gratuito vence el 8 de diciembre de 2026 y solo acepta conexiones por la red privada de Render.

## Implementado y comprobado localmente

| Área | Estado |
| --- | --- |
| Permisos | Protección de la actualización legacy de usuarios; aislamiento por organización y sitios. |
| Errores | Errores HTTP tipados y validaciones legibles. Sincronización distingue reintentos/rechazos y no filtra excepciones internas. |
| Evidencia | Presentación reversible de nombres, empresas, RUT, formularios, mensajes, importaciones y etiquetas 2D/3D. Alternar el control no produce escrituras. Se corrigió un producto visible en Operario. Las descargas advierten que contienen datos operativos sin censura. |
| Trazabilidad | Respuestas enriquecidas, búsqueda en servidor, historial confirmado separado de solicitudes y movimientos compensatorios vinculados al original. El reintento conserva ese vínculo. |
| Offline | Paquete completo por usuario/organización y sitios autorizados: productos, lotes, ubicaciones, reglas, tipos y saldos. Reemplazo atómico y vencimiento de escritura a las 72 horas; preservación de cola al vencer o fallar la preparación. |
| Recuperación | Persistencia antes del primer envío, UUID estable, orden de creación en cola, bloques de 100, recuperación de registros interrumpidos, resultados parciales, respuesta perdida y Web Locks entre pestañas. Se actualizan aprobaciones/rechazos para retirarlos del saldo provisional local. |
| Lotes/proveedor | Lote nuevo más entrada, proveedor tipado, validación de RUT y hora de captura. Reenvío idempotente sin duplicar lote/stock; conflicto si cambia el contenido. |
| PWA | Precarga de compilación sin duplicar index.html; preparación espera instalación del Service Worker. Actualización explícita y cola persistente. No declara listo un navegador sin soporte offline. |
| QR | Etiqueta SVG v2 con control de acceso, ID estable, lectura manual/URL y resolución local offline. Decodificador JS alternativo y pruebas con cámara simulada. Destino de traslado seleccionable desde el detalle. |
| Importación | Ruta física sede/jerarquía de zonas/posición, códigos nuevos P0001..., equivalencias ERP guardadas en perfiles y rechazo de coincidencias ambiguas; conservación de códigos originales. |
| Exportaciones | CSV con BOM, Excel, PDF y ZIP completo con nombres/códigos/lotes y filtros. Exportación de 20.002 movimientos comprobada en PostgreSQL. CORS expone totales. Corregidas las referencias UUID abreviadas de las descargas del dashboard. |
| BI | Ocupación por capacidad/unidad, agrupación diaria America/Santiago, vistas SQL y aprovisionamiento de cuenta de lectura por organización. Aislamiento probado con login PostgreSQL real. |
| CI | Workflows frontend/backend y PostgreSQL aprobados en GitHub. Integración de navegador aprobada en v3; se ejecuta al hacer push y también manualmente con referencia seleccionable del backend. |

## Correcciones adicionales de esta continuación

- Conservación de `id_movimiento_original` en almacenamiento, payload de sincronización y backend, probada también con PostgreSQL.
- Orden por `created_at` para no adelantar movimientos dependientes por el orden aleatorio de UUID.
- Resultados ajenos al bloque no modifican registros de otra cuenta.
- Consulta de resolución de solicitudes: aprobaciones/rechazos dejan de contar como saldo provisional; sin red se conserva el último estado conocido.
- Preparación maneja falta de espacio y fechas inválidas sin declarar éxito ni borrar la descarga anterior.
- Actualizada la revisión Alembic esperada por PostgreSQL y corregida una prueba webhook que mezclaba intentos de eventos ajenos al repetirse en la base desechable.
- Revisión visual PDF: cabeceras blancas sobre azul, anchos ajustados, metadatos y numeración de páginas.

## Verificación más reciente

- Backend SQLite: **168 pruebas aprobadas**. Tras el ajuste PDF se repitieron las pruebas de exportación y cierre de requisitos.
- Frontend: **40 pruebas aprobadas**, TypeScript sin errores y build de producción correcto.
- Playwright: **10 pruebas aprobadas**, cinco recorridos Chromium de escritorio y los mismos cinco en Pixel 7 emulado, con API real y SQLite desechable.
- Navegador: tres movimientos y lote nuevo offline, recarga/reapertura en otra pestaña sin red, respuesta perdida, vencimiento simulado de 73 horas, dos pestañas, cuenta de menor alcance y QR manual/URL offline.
- PostgreSQL **16.15 real** portable: migraciones desde cero hasta `g1h2i3j4k5l6`; una cabecera; `alembic check` sin operaciones pendientes; **11 pruebas aprobadas**.
- PostgreSQL cubre concurrencia, libro inmutable, JSONB, snapshot de exportación, recorrido global, webhook, recuperación compensatoria y exportación de **20.002 filas**.
- Cuenta BI: solo lee su organización; no lee tablas base/asignaciones ni escribe, incluso desactivando `default_transaction_read_only`. Una variable de organización enviada por el cliente no cambia su alcance.
- PDF de estrés con acentos, identificadores y nombres largos: páginas renderizadas e inspeccionadas. Capturas del modo evidencia inspeccionadas en Android emulado.
- Advertencias existentes: deprecaciones Python/pytest y paquete JS grande (~2 MB antes de comprimir). No impiden estas comprobaciones.

## Pendiente que requiere ambiente o participación externa

1. Conexión Power BI Service al piloto v3 guardada y comprobada en línea. Pendiente crear/cargar el modelo semántico y comprobar actualización de datos; no se ha probado Power BI Desktop.
2. CI frontend/backend ya ejecutado y aprobado en GitHub. Integración de navegador configurada para la rama v3.
3. Ensayar migración sobre copia autorizada de staging, respaldo/restauración y configuración del despliegue.
4. Validación con operarios en Android físico y Windows Chrome/Edge reales, cámara física y permanencia real de 72 horas. Emulación y reloj simulado no sustituyen esa prueba.
5. Piloto técnico separado ya desplegado en Render. Falta la cuenta inicial, datos autorizados y validación operativa con personas antes de utilizarlo como instalación de trabajo. No se usaron datos productivos.

## Avance Power BI — 8 de noviembre de 2026

- Usuario eligió el piloto v3 nuevo de Render. Se creó la organización vacía **SalmoTrack Piloto**, sin movimientos ni cuentas de aplicación.
- Rama backend `v3`: commits `3381c34` y `4b0a5e4`, subidos. CI SQLite/PostgreSQL aprobado: https://github.com/Gueremy/AXIOUS/actions/runs/42527614103.
- Aprovisionamiento opt-in, transaccional e idempotente; contraseña generada por Render en `POWER_BI_PASSWORD`, nunca mostrada en chat/logs/repositorio.
- Prueba nueva migra una base temporal con propietario no superusuario y verifica repetición, ausencia de datos, privilegios y lectura restringida. Las dos pruebas BI locales pasan; CI incluye el nuevo caso.
- Render confirmó en logs la conexión efectiva del lector a las seis vistas, sin acceso a tablas base ni escritura, el 2026-11-08 21:56:37 UTC.
- Cuenta SQL: `salmotrack_bi_dfd78b59_a241_5713_ade4_e4bb74453f27`.
- Power BI autenticado en cuenta INACAP; Mi área de trabajo sin modelo SalmoTrack. Interfaz Acerca de confirma región Centro-sur de EE. UU. (Texas).
- Render confirmó aplicada la lista de 22 rangos IPv4 `PowerBI.SouthCentralUS` del archivo oficial Microsoft 2026-11-02. No acceso general ni IP local. Revisar lista semanalmente.
- Usuario completó la entrada privada de los datos de conexión. Power BI Service muestra guardada **SalmoTrack Piloto v3**, tipo PostgreSQL, con SEBASTIAN IGNACIO como usuario visible.
- El 8 de noviembre se pulsó **Comprobar el estado** y la interfaz pasó de **Cargando** a **En línea**. Esto acredita conexión desde Power BI a PostgreSQL, además de la verificación SQL del lector realizada en Render.
- Evidencia: `power-bi-connection-online.jpg`. Página: https://app.powerbi.com/groups/me/gateways?experience=power-bi.
- Conexión efectiva completada. Pendiente, como trabajo posterior, crear/cargar modelo semántico, informe y comprobar actualización. No se creó contenido de ejemplo ni se habilitó una prueba de licencia/capacidad.

## Para retomar

Ver `VALIDATION.md`. PostgreSQL portable: `backend/backend/.cache/postgres/`, ignorado por Git. Capturas: `frontend/test-results/`. Ruflo MCP fue buscado y no estaba disponible en esta sesión.
