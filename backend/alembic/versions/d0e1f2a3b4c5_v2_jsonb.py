"""Use JSONB for configurable v2 documents on PostgreSQL.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "d0e1f2a3b4c5"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


DOCUMENT_COLUMNS = {
    "v2_alerta": ("metadatos",),
    "v2_esquema_atributos": ("schema_json",),
    "v2_importacion_job": ("resumen",),
    "v2_inconsistencia": ("datos_crudos",),
    "v2_item": ("atributos",),
    "v2_lote": ("atributos",),
    "v2_mapping_profile": ("mapeo",),
    "v2_movimiento": ("atributos",),
    "v2_organizacion": ("configuracion",),
    "v2_organizacion_modulo": ("configuracion",),
    "v2_regla_alerta": ("configuracion",),
    "v2_regla_ubicacion": ("configuracion",),
    "v2_sitio": ("atributos",),
    "v2_solicitud_movimiento": ("atributos",),
    "v2_ubicacion": ("atributos", "layout"),
    "v2_zona": ("atributos", "layout"),
}


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, columns in DOCUMENT_COLUMNS.items():
        for column in columns:
            op.alter_column(table, column, existing_type=sa.JSON(), type_=postgresql.JSONB(),
                            postgresql_using=f"{column}::jsonb")


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, columns in DOCUMENT_COLUMNS.items():
        for column in columns:
            op.alter_column(table, column, existing_type=postgresql.JSONB(), type_=sa.JSON(),
                            postgresql_using=f"{column}::json")
