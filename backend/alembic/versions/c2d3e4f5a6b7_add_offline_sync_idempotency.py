"""add offline sync idempotency

Revision ID: c2d3e4f5a6b7
Revises: a1b2c3d4e5f6
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("movimiento", sa.Column("uuid_local", sa.String(length=36), nullable=True))
    op.create_index("ix_movimiento_uuid_local", "movimiento", ["uuid_local"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_movimiento_uuid_local", table_name="movimiento")
    op.drop_column("movimiento", "uuid_local")
