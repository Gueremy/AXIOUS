"""add_v2_generic_domain

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-12 15:17:00.000000

Fase 0B: Agrega el modelo genérico multi-organización (v2):
- v2_organizacion
- v2_sitio
- v2_zona (jerárquica)
- v2_ubicacion
- v2_item
- v2_lote
- v2_esquema_atributos
- v2_saldo_stock
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. v2_organizacion
    op.create_table(
        'v2_organizacion',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('nombre', sa.String(length=150), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('configuracion', sa.JSON(), nullable=False),
        sa.Column('fecha_creacion', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_v2_organizacion_slug', 'v2_organizacion', ['slug'], unique=True)

    # 2. v2_sitio
    op.create_table(
        'v2_sitio',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('id_organizacion', sa.String(length=36), nullable=False),
        sa.Column('codigo', sa.String(length=50), nullable=False),
        sa.Column('nombre', sa.String(length=150), nullable=False),
        sa.Column('tipo', sa.String(length=50), nullable=False),
        sa.Column('descripcion', sa.String(length=300), nullable=True),
        sa.Column('ubicacion_geografica', sa.String(length=200), nullable=True),
        sa.Column('atributos', sa.JSON(), nullable=False),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('fecha_creacion', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['id_organizacion'], ['v2_organizacion.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('id_organizacion', 'codigo', name='uq_sitio_org_codigo'),
    )
    op.create_index('ix_v2_sitio_id_organizacion', 'v2_sitio', ['id_organizacion'], unique=False)

    # 3. v2_zona (jerárquica)
    op.create_table(
        'v2_zona',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('id_organizacion', sa.String(length=36), nullable=False),
        sa.Column('id_sitio', sa.String(length=36), nullable=False),
        sa.Column('id_zona_padre', sa.String(length=36), nullable=True),
        sa.Column('codigo', sa.String(length=50), nullable=False),
        sa.Column('nombre', sa.String(length=150), nullable=False),
        sa.Column('tipo', sa.String(length=50), nullable=False),
        sa.Column('layout', sa.JSON(), nullable=False),
        sa.Column('atributos', sa.JSON(), nullable=False),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('fecha_creacion', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['id_organizacion'], ['v2_organizacion.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['id_sitio'], ['v2_sitio.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['id_zona_padre'], ['v2_zona.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('id_sitio', 'codigo', name='uq_zona_sitio_codigo'),
    )
    op.create_index('ix_v2_zona_id_organizacion', 'v2_zona', ['id_organizacion'], unique=False)
    op.create_index('ix_v2_zona_id_sitio', 'v2_zona', ['id_sitio'], unique=False)
    op.create_index('ix_v2_zona_id_zona_padre', 'v2_zona', ['id_zona_padre'], unique=False)

    # 4. v2_ubicacion
    op.create_table(
        'v2_ubicacion',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('id_organizacion', sa.String(length=36), nullable=False),
        sa.Column('id_zona', sa.String(length=36), nullable=False),
        sa.Column('codigo', sa.String(length=50), nullable=False),
        sa.Column('capacidad_maxima', sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column('unidad_capacidad', sa.String(length=20), nullable=False),
        sa.Column('ocupacion_actual', sa.Numeric(precision=12, scale=4), nullable=False, server_default=sa.text('0.0')),
        sa.Column('permite_mezcla_lotes', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('estado', sa.String(length=30), nullable=False, server_default=sa.text("'disponible'")),
        sa.Column('layout', sa.JSON(), nullable=False),
        sa.Column('atributos', sa.JSON(), nullable=False),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('fecha_creacion', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint('capacidad_maxima >= 0', name='chk_ubicacion_capacidad_positiva'),
        sa.ForeignKeyConstraint(['id_organizacion'], ['v2_organizacion.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['id_zona'], ['v2_zona.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('id_zona', 'codigo', name='uq_ubicacion_zona_codigo'),
    )
    op.create_index('ix_v2_ubicacion_id_organizacion', 'v2_ubicacion', ['id_organizacion'], unique=False)
    op.create_index('ix_v2_ubicacion_id_zona', 'v2_ubicacion', ['id_zona'], unique=False)

    # 5. v2_item
    op.create_table(
        'v2_item',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('id_organizacion', sa.String(length=36), nullable=False),
        sa.Column('codigo', sa.String(length=50), nullable=False),
        sa.Column('nombre', sa.String(length=150), nullable=False),
        sa.Column('categoria', sa.String(length=50), nullable=False),
        sa.Column('unidad_medida', sa.String(length=20), nullable=False),
        sa.Column('atributos', sa.JSON(), nullable=False),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('fecha_creacion', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['id_organizacion'], ['v2_organizacion.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('id_organizacion', 'codigo', name='uq_item_org_codigo'),
    )
    op.create_index('ix_v2_item_id_organizacion', 'v2_item', ['id_organizacion'], unique=False)

    # 6. v2_lote
    op.create_table(
        'v2_lote',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('id_organizacion', sa.String(length=36), nullable=False),
        sa.Column('id_item', sa.String(length=36), nullable=False),
        sa.Column('numero_lote', sa.String(length=100), nullable=False),
        sa.Column('fecha_fabricacion', sa.DateTime(timezone=True), nullable=True),
        sa.Column('fecha_vencimiento', sa.DateTime(timezone=True), nullable=True),
        sa.Column('atributos', sa.JSON(), nullable=False),
        sa.Column('estado', sa.String(length=30), nullable=False, server_default=sa.text("'activo'")),
        sa.Column('fecha_creacion', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['id_item'], ['v2_item.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['id_organizacion'], ['v2_organizacion.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('id_item', 'numero_lote', name='uq_lote_item_numero'),
    )
    op.create_index('ix_v2_lote_id_organizacion', 'v2_lote', ['id_organizacion'], unique=False)
    op.create_index('ix_v2_lote_id_item', 'v2_lote', ['id_item'], unique=False)
    op.create_index('ix_v2_lote_fecha_vencimiento', 'v2_lote', ['fecha_vencimiento'], unique=False)

    # 7. v2_esquema_atributos
    op.create_table(
        'v2_esquema_atributos',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('id_organizacion', sa.String(length=36), nullable=False),
        sa.Column('entidad', sa.String(length=50), nullable=False),
        sa.Column('nombre', sa.String(length=100), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('schema_json', sa.JSON(), nullable=False),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('fecha_creacion', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['id_organizacion'], ['v2_organizacion.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('id_organizacion', 'entidad', 'nombre', 'version', name='uq_esquema_org_entidad_ver'),
    )
    op.create_index('ix_v2_esquema_atributos_id_organizacion', 'v2_esquema_atributos', ['id_organizacion'], unique=False)

    # 8. v2_saldo_stock
    op.create_table(
        'v2_saldo_stock',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('id_organizacion', sa.String(length=36), nullable=False),
        sa.Column('id_ubicacion', sa.String(length=36), nullable=False),
        sa.Column('id_item', sa.String(length=36), nullable=False),
        sa.Column('id_lote', sa.String(length=36), nullable=True),
        sa.Column('cantidad', sa.Numeric(precision=12, scale=4), nullable=False, server_default=sa.text('0.0')),
        sa.Column('unidad_medida', sa.String(length=20), nullable=False),
        sa.Column('fecha_actualizacion', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint('cantidad >= 0', name='chk_saldo_cantidad_no_negativa'),
        sa.ForeignKeyConstraint(['id_item'], ['v2_item.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['id_lote'], ['v2_lote.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['id_organizacion'], ['v2_organizacion.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['id_ubicacion'], ['v2_ubicacion.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('id_ubicacion', 'id_item', 'id_lote', name='uq_saldo_ubicacion_item_lote'),
    )
    op.create_index('ix_v2_saldo_stock_id_organizacion', 'v2_saldo_stock', ['id_organizacion'], unique=False)
    op.create_index('ix_v2_saldo_stock_id_ubicacion', 'v2_saldo_stock', ['id_ubicacion'], unique=False)
    op.create_index('ix_v2_saldo_stock_id_item', 'v2_saldo_stock', ['id_item'], unique=False)
    op.create_index('ix_v2_saldo_stock_id_lote', 'v2_saldo_stock', ['id_lote'], unique=False)


def downgrade() -> None:
    op.drop_table('v2_saldo_stock')
    op.drop_table('v2_esquema_atributos')
    op.drop_table('v2_lote')
    op.drop_table('v2_item')
    op.drop_table('v2_ubicacion')
    op.drop_table('v2_zona')
    op.drop_table('v2_sitio')
    op.drop_table('v2_organizacion')
