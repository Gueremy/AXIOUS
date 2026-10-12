"""add_v2_movements_and_trigger

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-12 15:28:00.000000

Fase 1A: Agrega tablas de movimientos genéricos y trigger de inmutabilidad estricta:
- v2_tipo_movimiento
- v2_solicitud_movimiento
- v2_movimiento
- Trigger PostgreSQL trg_v2_movimiento_immutable
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. v2_tipo_movimiento
    op.create_table(
        'v2_tipo_movimiento',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('id_organizacion', sa.String(length=36), nullable=False),
        sa.Column('codigo', sa.String(length=50), nullable=False),
        sa.Column('nombre', sa.String(length=100), nullable=False),
        sa.Column('efecto_stock', sa.String(length=20), nullable=False),
        sa.Column('requiere_origen', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('requiere_destino', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('requiere_aprobacion', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.ForeignKeyConstraint(['id_organizacion'], ['v2_organizacion.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('id_organizacion', 'codigo', name='uq_tipo_mov_org_codigo'),
    )
    op.create_index('ix_v2_tipo_movimiento_id_organizacion', 'v2_tipo_movimiento', ['id_organizacion'], unique=False)

    # 2. v2_solicitud_movimiento
    op.create_table(
        'v2_solicitud_movimiento',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('id_organizacion', sa.String(length=36), nullable=False),
        sa.Column('id_tipo_movimiento', sa.String(length=36), nullable=False),
        sa.Column('id_item', sa.String(length=36), nullable=False),
        sa.Column('id_lote', sa.String(length=36), nullable=True),
        sa.Column('id_ubicacion_origen', sa.String(length=36), nullable=True),
        sa.Column('id_ubicacion_destino', sa.String(length=36), nullable=True),
        sa.Column('id_usuario_solicitante', sa.String(length=36), nullable=False),
        sa.Column('id_usuario_aprobador', sa.String(length=36), nullable=True),
        sa.Column('cantidad', sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column('unidad_medida', sa.String(length=20), nullable=False),
        sa.Column('estado', sa.String(length=20), nullable=False, server_default=sa.text("'pendiente'")),
        sa.Column('motivo_rechazo', sa.String(length=300), nullable=True),
        sa.Column('observaciones', sa.String(length=300), nullable=True),
        sa.Column('uuid_local', sa.String(length=36), nullable=True),
        sa.Column('atributos', sa.JSON(), nullable=False),
        sa.Column('fecha_creacion', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('fecha_resolucion', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['id_item'], ['v2_item.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['id_lote'], ['v2_lote.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['id_organizacion'], ['v2_organizacion.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['id_tipo_movimiento'], ['v2_tipo_movimiento.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['id_ubicacion_destino'], ['v2_ubicacion.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['id_ubicacion_origen'], ['v2_ubicacion.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['id_usuario_aprobador'], ['usuario.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['id_usuario_solicitante'], ['usuario.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('id_organizacion', 'uuid_local', name='uq_solicitud_org_uuid_local'),
    )
    op.create_index('ix_v2_solicitud_movimiento_id_organizacion', 'v2_solicitud_movimiento', ['id_organizacion'], unique=False)
    op.create_index('ix_v2_solicitud_movimiento_id_item', 'v2_solicitud_movimiento', ['id_item'], unique=False)
    op.create_index('ix_v2_solicitud_movimiento_estado', 'v2_solicitud_movimiento', ['estado'], unique=False)

    # 3. v2_movimiento (Inmutable)
    op.create_table(
        'v2_movimiento',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('id_organizacion', sa.String(length=36), nullable=False),
        sa.Column('id_solicitud', sa.String(length=36), nullable=True),
        sa.Column('id_tipo_movimiento', sa.String(length=36), nullable=False),
        sa.Column('id_movimiento_original', sa.String(length=36), nullable=True),
        sa.Column('id_item', sa.String(length=36), nullable=False),
        sa.Column('id_lote', sa.String(length=36), nullable=True),
        sa.Column('id_ubicacion_origen', sa.String(length=36), nullable=True),
        sa.Column('id_ubicacion_destino', sa.String(length=36), nullable=True),
        sa.Column('id_usuario', sa.String(length=36), nullable=False),
        sa.Column('id_usuario_aprobador', sa.String(length=36), nullable=True),
        sa.Column('cantidad', sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column('unidad_medida', sa.String(length=20), nullable=False),
        sa.Column('efecto_stock', sa.String(length=20), nullable=False),
        sa.Column('uuid_local', sa.String(length=36), nullable=True),
        sa.Column('atributos', sa.JSON(), nullable=False),
        sa.Column('fecha_hora', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('observaciones', sa.String(length=300), nullable=True),
        sa.ForeignKeyConstraint(['id_item'], ['v2_item.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['id_lote'], ['v2_lote.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['id_movimiento_original'], ['v2_movimiento.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['id_organizacion'], ['v2_organizacion.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['id_solicitud'], ['v2_solicitud_movimiento.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['id_tipo_movimiento'], ['v2_tipo_movimiento.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['id_ubicacion_destino'], ['v2_ubicacion.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['id_ubicacion_origen'], ['v2_ubicacion.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['id_usuario'], ['usuario.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['id_usuario_aprobador'], ['usuario.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('id_organizacion', 'uuid_local', name='uq_mov_v2_org_uuid_local'),
    )
    op.create_index('ix_v2_movimiento_id_organizacion', 'v2_movimiento', ['id_organizacion'], unique=False)
    op.create_index('ix_v2_movimiento_id_item', 'v2_movimiento', ['id_item'], unique=False)
    op.create_index('ix_v2_movimiento_id_lote', 'v2_movimiento', ['id_lote'], unique=False)
    op.create_index('ix_v2_movimiento_fecha_hora', 'v2_movimiento', ['fecha_hora'], unique=False)

    # 4. Trigger de inmutabilidad estricta sobre v2_movimiento (PostgreSQL)
    op.execute("""
        DO $$
        BEGIN
            CREATE OR REPLACE FUNCTION prevent_movimiento_v2_update_or_delete()
            RETURNS trigger AS $fn$
            BEGIN
                RAISE EXCEPTION
                    'Los movimientos de v2_movimiento son inmutables. '
                    'Para corregir un error, registre un nuevo movimiento compensatorio '
                    'referenciando id_movimiento_original.';
            END;
            $fn$ LANGUAGE plpgsql;

            DROP TRIGGER IF EXISTS trg_v2_movimiento_immutable ON v2_movimiento;

            CREATE TRIGGER trg_v2_movimiento_immutable
            BEFORE UPDATE OR DELETE ON v2_movimiento
            FOR EACH ROW EXECUTE FUNCTION prevent_movimiento_v2_update_or_delete();
        EXCEPTION WHEN undefined_function THEN
            -- Ignorar si la BD no es PostgreSQL (ej. SQLite en modo offline)
            NULL;
        END $$;
    """)


def downgrade() -> None:
    op.execute("""
        DROP TRIGGER IF EXISTS trg_v2_movimiento_immutable ON v2_movimiento;
        DROP FUNCTION IF EXISTS prevent_movimiento_v2_update_or_delete();
    """)
    op.drop_table('v2_movimiento')
    op.drop_table('v2_solicitud_movimiento')
    op.drop_table('v2_tipo_movimiento')
