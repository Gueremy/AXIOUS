"""Persist incoming integration event idempotency keys.

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
"""
from alembic import op
import sqlalchemy as sa

revision = "a3b4c5d6e7f8"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "v2_evento_entrante",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("id_organizacion", sa.String(36), sa.ForeignKey("v2_organizacion.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fuente", sa.String(100), nullable=False),
        sa.Column("id_evento_externo", sa.String(150), nullable=False),
        sa.Column("tipo_evento", sa.String(100), nullable=False),
        sa.Column("fecha_recepcion", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("id_organizacion", "fuente", "id_evento_externo", name="uq_v2_evento_entrante_clave"),
    )
    op.create_index("ix_v2_evento_entrante_id_organizacion", "v2_evento_entrante", ["id_organizacion"])


def downgrade() -> None:
    op.drop_index("ix_v2_evento_entrante_id_organizacion", table_name="v2_evento_entrante")
    op.drop_table("v2_evento_entrante")
