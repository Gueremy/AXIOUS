"""add_v2_organizacion_modulo

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-10-12 15:51:00.000000

Fase 2: Tabla v2_organizacion_modulo para registro de módulos activos y feature flags por organización.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, Sequence[str], None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'v2_organizacion_modulo',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('id_organizacion', sa.String(length=36), nullable=False),
        sa.Column('id_modulo', sa.String(length=50), nullable=False),
        sa.Column('habilitado', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('configuracion', sa.JSON(), nullable=False),
        sa.Column('fecha_activacion', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['id_organizacion'], ['v2_organizacion.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('id_organizacion', 'id_modulo', name='uq_v2_org_modulo'),
    )
    op.create_index('ix_v2_organizacion_modulo_id_organizacion', 'v2_organizacion_modulo', ['id_organizacion'], unique=False)
    op.create_index('ix_v2_organizacion_modulo_id_modulo', 'v2_organizacion_modulo', ['id_modulo'], unique=False)


def downgrade() -> None:
    op.drop_table('v2_organizacion_modulo')
