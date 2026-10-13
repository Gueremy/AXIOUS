"""Align movement lookup indexes with the v2 ORM.

Revision ID: b4c5d6e7f809
Revises: a3b4c5d6e7f8
"""
from alembic import op

revision = "b4c5d6e7f809"
down_revision = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None

MOVEMENT_COLUMNS = (
    "id_movimiento_original", "id_solicitud", "id_tipo_movimiento",
    "id_ubicacion_destino", "id_ubicacion_origen", "id_usuario", "id_usuario_aprobador",
)
REQUEST_COLUMNS = (
    "id_lote", "id_tipo_movimiento", "id_ubicacion_destino", "id_ubicacion_origen",
    "id_usuario_aprobador", "id_usuario_solicitante",
)


def upgrade() -> None:
    for column in MOVEMENT_COLUMNS:
        op.create_index(f"ix_v2_movimiento_{column}", "v2_movimiento", [column])
    for column in REQUEST_COLUMNS:
        op.create_index(f"ix_v2_solicitud_movimiento_{column}", "v2_solicitud_movimiento", [column])


def downgrade() -> None:
    for column in REQUEST_COLUMNS:
        op.drop_index(f"ix_v2_solicitud_movimiento_{column}", table_name="v2_solicitud_movimiento")
    for column in MOVEMENT_COLUMNS:
        op.drop_index(f"ix_v2_movimiento_{column}", table_name="v2_movimiento")
