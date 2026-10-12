"""add_v2_alertas_and_reglas

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-10-12 15:42:00.000000

Fase 1D: Agrega tablas v2_regla_alerta y v2_alerta para reglas de alertas configurables y trazables.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Tabla v2_regla_alerta
    op.create_table(
        'v2_regla_alerta',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('id_organizacion', sa.String(length=36), nullable=False),
        sa.Column('codigo', sa.String(length=50), nullable=False),
        sa.Column('nombre', sa.String(length=100), nullable=False),
        sa.Column('tipo', sa.String(length=50), nullable=False),
        sa.Column('configuracion', sa.JSON(), nullable=False),
        sa.Column('severidad', sa.String(length=20), nullable=False, server_default='aviso'),
        sa.Column('habilitada', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('fecha_creacion', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('fecha_actualizacion', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['id_organizacion'], ['v2_organizacion.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('id_organizacion', 'codigo', name='uq_v2_regla_alerta_org_codigo'),
    )
    op.create_index('ix_v2_regla_alerta_id_organizacion', 'v2_regla_alerta', ['id_organizacion'], unique=False)

    # 2. Tabla v2_alerta
    op.create_table(
        'v2_alerta',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('id_organizacion', sa.String(length=36), nullable=False),
        sa.Column('id_regla', sa.String(length=36), nullable=True),
        sa.Column('id_sitio', sa.String(length=36), nullable=True),
        sa.Column('id_ubicacion', sa.String(length=36), nullable=True),
        sa.Column('id_item', sa.String(length=36), nullable=True),
        sa.Column('id_lote', sa.String(length=36), nullable=True),
        sa.Column('tipo', sa.String(length=50), nullable=False),
        sa.Column('severidad', sa.String(length=20), nullable=False),
        sa.Column('titulo', sa.String(length=150), nullable=False),
        sa.Column('descripcion', sa.String(length=500), nullable=False),
        sa.Column('estado', sa.String(length=20), nullable=False, server_default='activa'),
        sa.Column('id_usuario_revision', sa.String(length=36), nullable=True),
        sa.Column('fecha_generacion', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('fecha_revision', sa.DateTime(timezone=True), nullable=True),
        sa.Column('fecha_resolucion', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadatos', sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(['id_organizacion'], ['v2_organizacion.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['id_regla'], ['v2_regla_alerta.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['id_sitio'], ['v2_sitio.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['id_ubicacion'], ['v2_ubicacion.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['id_item'], ['v2_item.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['id_lote'], ['v2_lote.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['id_usuario_revision'], ['usuario.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_v2_alerta_id_organizacion', 'v2_alerta', ['id_organizacion'], unique=False)
    op.create_index('ix_v2_alerta_id_regla', 'v2_alerta', ['id_regla'], unique=False)
    op.create_index('ix_v2_alerta_id_sitio', 'v2_alerta', ['id_sitio'], unique=False)
    op.create_index('ix_v2_alerta_id_ubicacion', 'v2_alerta', ['id_ubicacion'], unique=False)
    op.create_index('ix_v2_alerta_id_item', 'v2_alerta', ['id_item'], unique=False)
    op.create_index('ix_v2_alerta_id_lote', 'v2_alerta', ['id_lote'], unique=False)


def downgrade() -> None:
    op.drop_table('v2_alerta')
    op.drop_table('v2_regla_alerta')
