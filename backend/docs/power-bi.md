# Conexión de Power BI

1. Aplicar `alembic upgrade head` en staging con PostgreSQL 16 y respaldo comprobado.
2. Ejecutar `python scripts/provision_bi.py UUID_ORGANIZACION` con una conexión administrativa configurada. El script solicita la contraseña en privado y genera el nombre de la cuenta. Requiere al menos 16 caracteres.
3. Conectar Power BI Desktop mediante PostgreSQL, TLS y esa cuenta. Seleccionar únicamente las vistas del esquema `salmotrack_bi`.
4. Relacionar dimensiones por sus identificadores. `stock` representa saldos por producto y lote; `ocupacion` tiene una fila por ubicación. Usar `ocupacion` para calcular capacidad sin duplicarla por cada lote de stock.
5. Para Power BI Service, configurar la conexión de actualización y el gateway correspondiente a la red del servidor. Las credenciales nunca se incluyen en React.

Las vistas filtran por la cuenta PostgreSQL realmente conectada (`session_user`). La cuenta no puede escribir ni leer tablas base o la tabla de asignaciones. No se utiliza una variable de organización modificable por Power BI.

Validar con dos organizaciones: cada cuenta debe ver sus propios datos; `SELECT` a tablas base y cualquier escritura deben ser rechazados. Las pruebas `tests_postgres/test_bi_readonly.py` requieren la base de pruebas aislada indicada en la guía de QA. No ejecutar esas pruebas en producción.

El aprovisionamiento local no configura la red, TLS, gateway ni credenciales de Power BI Service. Esas comprobaciones requieren el ambiente de staging real.

## Piloto v3 en Render

El Blueprint `deploy/render-v3.yaml` activa `SALMOTRACK_BOOTSTRAP_PILOT_BI=1`
y genera `POWER_BI_PASSWORD` en Render. Después de migrar, el arranque crea
la organización vacía **SalmoTrack Piloto** y su cuenta de lectura. No crea
usuarios de la aplicación ni movimientos. La operación es transaccional e
idempotente; rechaza una base con otras organizaciones si el piloto no existe.
La contraseña no se registra ni se incorpora al repositorio. Se consulta de
forma privada en Environment del servicio API para introducirla en Power BI.

La cuenta creada se anuncia por nombre en los logs de arranque. Seleccionar
PostgreSQL, base `salmotrack_v3`, autenticación básica, conexión cifrada y
privacidad Organización. Obtener el hostname externo de Connect en la base
Render, sin usar su usuario administrador en Power BI.

La base sigue con `ipAllowList: []`. Antes de guardar/probar la conexión hay
que permitir exclusivamente los rangos de salida del servicio Power BI
correspondiente o configurar un gateway con salida de IP conocida. No abrir
`0.0.0.0/0`. Una conexión configurada no equivale a un modelo semántico o un
informe publicado: verificar por separado conexión, carga y actualización.

La prueba `tests_postgres/test_pilot_bootstrap.py` migra una base temporal con
un propietario no superusuario y comprueba repetición, ausencia de stock,
privilegios del lector y rechazo a tablas base/escritura.
