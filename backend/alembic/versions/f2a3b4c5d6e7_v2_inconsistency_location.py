"""Attach reconciled inconsistencies to an exact location.

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
"""
from alembic import op
import sqlalchemy as sa


revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("v2_inconsistencia", sa.Column("id_ubicacion", sa.String(36), nullable=True))
    op.create_foreign_key("fk_v2_inconsistencia_ubicacion", "v2_inconsistencia", "v2_ubicacion",
                          ["id_ubicacion"], ["id"], ondelete="SET NULL")
    op.create_index("ix_v2_inconsistencia_id_ubicacion", "v2_inconsistencia", ["id_ubicacion"])
    # Historical rows are associated only when their location code is unique in the tenant.
    op.execute("""
        UPDATE v2_inconsistencia AS inc SET id_ubicacion = resolved.id
        FROM (
          SELECT u.id_organizacion, u.codigo, MIN(u.id) AS id
          FROM v2_ubicacion AS u
          GROUP BY u.id_organizacion, u.codigo
          HAVING COUNT(*) = 1
        ) AS resolved
        WHERE inc.id_organizacion = resolved.id_organizacion
          AND inc.codigo_ubicacion = resolved.codigo
    """)


def downgrade() -> None:
    op.drop_index("ix_v2_inconsistencia_id_ubicacion", table_name="v2_inconsistencia")
    op.drop_constraint("fk_v2_inconsistencia_ubicacion", "v2_inconsistencia", type_="foreignkey")
    op.drop_column("v2_inconsistencia", "id_ubicacion")
