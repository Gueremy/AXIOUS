"""Read-only analytic views scoped to the authenticated PostgreSQL login.

Revision ID: g1h2i3j4k5l6
Revises: c5d6e7f80910
"""
from alembic import op

revision = "g1h2i3j4k5l6"
down_revision = "c5d6e7f80910"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SCHEMA salmotrack_bi")
    op.execute("REVOKE ALL ON SCHEMA salmotrack_bi FROM PUBLIC")
    op.execute("""CREATE TABLE salmotrack_bi.principal (
        login_name text PRIMARY KEY,
        id_organizacion varchar(36) NOT NULL REFERENCES v2_organizacion(id) ON DELETE CASCADE
    )""")
    op.execute("REVOKE ALL ON salmotrack_bi.principal FROM PUBLIC")
    # session_user is the login, not a mutable client-supplied organization setting.
    scope = "(SELECT id_organizacion FROM salmotrack_bi.principal WHERE login_name = session_user)"
    views = {
        "sitios": f"SELECT id AS id_sitio, codigo, nombre, tipo FROM v2_sitio WHERE id_organizacion = {scope}",
        "items": f"SELECT id AS id_item, codigo, nombre, categoria, unidad_medida FROM v2_item WHERE id_organizacion = {scope}",
        "ocupacion": f"""SELECT u.id AS id_ubicacion, s.codigo AS sede, z.codigo AS zona, u.codigo AS ubicacion,
            u.capacidad_maxima, u.ocupacion_actual, u.unidad_capacidad,
            CASE WHEN u.capacidad_maxima > 0 THEN 100*u.ocupacion_actual/u.capacidad_maxima ELSE 0 END AS porcentaje_ocupacion
            FROM v2_ubicacion u JOIN v2_zona z ON z.id=u.id_zona JOIN v2_sitio s ON s.id=z.id_sitio
            WHERE u.id_organizacion = {scope}""",
        "stock": f"""SELECT s.id, u.codigo AS ubicacion, z.codigo AS zona, site.codigo AS sede,
            i.codigo AS codigo_producto, i.nombre AS producto, l.numero_lote, l.fecha_vencimiento,
            s.cantidad, s.unidad_medida, s.fecha_actualizacion
            FROM v2_saldo_stock s JOIN v2_ubicacion u ON u.id=s.id_ubicacion
            JOIN v2_zona z ON z.id=u.id_zona JOIN v2_sitio site ON site.id=z.id_sitio
            JOIN v2_item i ON i.id=s.id_item LEFT JOIN v2_lote l ON l.id=s.id_lote
            WHERE s.id_organizacion = {scope}""",
        "movimientos": f"""SELECT m.id, m.fecha_hora,
            m.fecha_hora AT TIME ZONE 'America/Santiago' AS fecha_hora_chile,
            t.nombre AS tipo, m.efecto_stock, i.codigo AS codigo_producto, i.nombre AS producto,
            l.numero_lote, orig.codigo AS origen, dest.codigo AS destino, m.cantidad, m.unidad_medida,
            u.codigo_empleado AS operario
            FROM v2_movimiento m JOIN v2_tipo_movimiento t ON t.id=m.id_tipo_movimiento
            JOIN v2_item i ON i.id=m.id_item LEFT JOIN v2_lote l ON l.id=m.id_lote
            LEFT JOIN v2_ubicacion orig ON orig.id=m.id_ubicacion_origen
            LEFT JOIN v2_ubicacion dest ON dest.id=m.id_ubicacion_destino
            JOIN usuario u ON u.id=m.id_usuario
            WHERE m.id_organizacion = {scope}""",
        "inconsistencias": f"""SELECT id, fila_origen, tipo_inconsistencia, motivo,
            codigo_ubicacion, codigo_item, numero_lote, cantidad_externa, resuelto, fecha_deteccion
            FROM v2_inconsistencia WHERE id_organizacion = {scope}""",
    }
    for name, query in views.items():
        op.execute(f"CREATE VIEW salmotrack_bi.{name} WITH (security_barrier=true) AS {query}")
        op.execute(f"REVOKE ALL ON salmotrack_bi.{name} FROM PUBLIC")


def downgrade():
    for name in ("inconsistencias", "movimientos", "stock", "ocupacion", "items", "sitios"):
        op.execute(f"DROP VIEW salmotrack_bi.{name}")
    op.execute("DROP TABLE salmotrack_bi.principal")
    op.execute("DROP SCHEMA salmotrack_bi")
