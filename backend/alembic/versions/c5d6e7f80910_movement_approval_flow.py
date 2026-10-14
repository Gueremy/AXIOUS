"""Configurable approval flow per movement type.

Revision ID: c5d6e7f80910
Revises: b4c5d6e7f809
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "c5d6e7f80910"
down_revision = "b4c5d6e7f809"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("v2_tipo_movimiento", sa.Column(
        "flujo_aprobacion", sa.JSON().with_variant(JSONB(), "postgresql"),
        nullable=False, server_default=sa.text("'{}'"),
    ))


def downgrade() -> None:
    op.drop_column("v2_tipo_movimiento", "flujo_aprobacion")
