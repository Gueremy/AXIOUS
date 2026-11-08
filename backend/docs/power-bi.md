# Conexión de Power BI

1. Aplicar `alembic upgrade head` en staging con PostgreSQL 16 y respaldo comprobado.
2. Ejecutar `python scripts/provision_bi.py UUID_ORGANIZACION` con una conexión administrativa configurada. El script solicita la contraseña en privado y genera el nombre de la cuenta. Requiere al menos 16 caracteres.
3. Conectar Power BI Desktop mediante PostgreSQL, TLS y esa cuenta. Seleccionar únicamente las vistas del esquema `salmotrack_bi`.
4. Relacionar dimensiones por sus identificadores. `stock` representa saldos por producto y lote; `ocupacion` tiene una fila por ubicación. Usar `ocupacion` para calcular capacidad sin duplicarla por cada lote de stock.
5. Para Power BI Service, configurar la conexión de actualización y el gateway correspondiente a la red del servidor. Las credenciales nunca se incluyen en React.

Las vistas filtran por la cuenta PostgreSQL realmente conectada (`session_user`). La cuenta no puede escribir ni leer tablas base o la tabla de asignaciones. No se utiliza una variable de organización modificable por Power BI.

Validar con dos organizaciones: cada cuenta debe ver sus propios datos; `SELECT` a tablas base y cualquier escritura deben ser rechazados. Las pruebas `tests_postgres/test_bi_readonly.py` requieren la base de pruebas aislada indicada en la guía de QA. No ejecutar esas pruebas en producción.

El aprovisionamiento local no configura la red, TLS, gateway ni credenciales de Power BI Service. Esas comprobaciones requieren el ambiente de staging real.
