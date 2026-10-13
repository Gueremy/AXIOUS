"""Prevent duplicate approval and duplicate stock balances without a lot.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
"""
from alembic import op
import sqlalchemy as sa


revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_mov_v2_solicitud", "v2_movimiento", ["id_solicitud"])
    op.create_index(
        "uq_saldo_sin_lote",
        "v2_saldo_stock",
        ["id_ubicacion", "id_item"],
        unique=True,
        postgresql_where=sa.text("id_lote IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_saldo_sin_lote", table_name="v2_saldo_stock")
    op.drop_constraint("uq_mov_v2_solicitud", "v2_movimiento", type_="unique")
