"""add_v2_regla_ubicacion

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-12 15:34:00.000000

Fase 1B: Agrega tabla v2_regla_ubicacion para el motor de reglas configurable.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'v2_regla_ubicacion',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('id_organizacion', sa.String(length=36), nullable=False),
        sa.Column('id_sitio', sa.String(length=36), nullable=True),
        sa.Column('id_zona', sa.String(length=36), nullable=True),
        sa.Column('id_ubicacion', sa.String(length=36), nullable=True),
        sa.Column('codigo', sa.String(length=50), nullable=False),
        sa.Column('nombre', sa.String(length=100), nullable=False),
        sa.Column('tipo_regla', sa.String(length=50), nullable=False),
        sa.Column('configuracion', sa.JSON(), nullable=False),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('fecha_creacion', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['id_organizacion'], ['v2_organizacion.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['id_sitio'], ['v2_sitio.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['id_ubicacion'], ['v2_ubicacion.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['id_zona'], ['v2_zona.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_v2_regla_ubicacion_id_organizacion', 'v2_regla_ubicacion', ['id_organizacion'], unique=False)
    op.create_index('ix_v2_regla_ubicacion_id_sitio', 'v2_regla_ubicacion', ['id_sitio'], unique=False)
    op.create_index('ix_v2_regla_ubicacion_id_zona', 'v2_regla_ubicacion', ['id_zona'], unique=False)
    op.create_index('ix_v2_regla_ubicacion_id_ubicacion', 'v2_regla_ubicacion', ['id_ubicacion'], unique=False)


def downgrade() -> None:
    op.drop_table('v2_regla_ubicacion')
