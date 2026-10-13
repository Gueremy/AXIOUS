"""Durable, tenant-scoped webhook destinations and delivery queue.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "e1f2a3b4c5d6"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    document = sa.JSON().with_variant(JSONB(), "postgresql")
    op.create_table(
        "v2_webhook_destino",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("id_organizacion", sa.String(36), sa.ForeignKey("v2_organizacion.id", ondelete="CASCADE"), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("secreto_cifrado", sa.String(1024), nullable=False),
        sa.Column("eventos", document, nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("fecha_creacion", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("id_organizacion", "url", name="uq_webhook_destino_org_url"),
    )
    op.create_index("ix_v2_webhook_destino_id_organizacion", "v2_webhook_destino", ["id_organizacion"])
    op.create_table(
        "v2_webhook_entrega",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("id_organizacion", sa.String(36), sa.ForeignKey("v2_organizacion.id", ondelete="CASCADE"), nullable=False),
        sa.Column("id_destino", sa.String(36), sa.ForeignKey("v2_webhook_destino.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tipo_evento", sa.String(100), nullable=False),
        sa.Column("id_evento", sa.String(100), nullable=False),
        sa.Column("payload", document, nullable=False),
        sa.Column("estado", sa.String(20), nullable=False),
        sa.Column("intentos", sa.Integer(), nullable=False),
        sa.Column("proximo_intento", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("fecha_creacion", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("fecha_envio", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("id_destino", "tipo_evento", "id_evento", name="uq_webhook_entrega_evento"),
    )
    op.create_index("ix_v2_webhook_entrega_id_organizacion", "v2_webhook_entrega", ["id_organizacion"])
    op.create_index("ix_v2_webhook_entrega_id_destino", "v2_webhook_entrega", ["id_destino"])
    op.create_index("ix_v2_webhook_entrega_due", "v2_webhook_entrega", ["estado", "proximo_intento"])


def downgrade() -> None:
    op.drop_index("ix_v2_webhook_entrega_due", table_name="v2_webhook_entrega")
    op.drop_index("ix_v2_webhook_entrega_id_destino", table_name="v2_webhook_entrega")
    op.drop_index("ix_v2_webhook_entrega_id_organizacion", table_name="v2_webhook_entrega")
    op.drop_table("v2_webhook_entrega")
    op.drop_index("ix_v2_webhook_destino_id_organizacion", table_name="v2_webhook_destino")
    op.drop_table("v2_webhook_destino")
