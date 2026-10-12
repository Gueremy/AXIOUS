"""add_v2_importacion_and_conciliacion

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-10-12 15:44:00.000000

Fase 1E: Tablas v2_mapping_profile, v2_importacion_job y v2_inconsistencia para conciliación ERP/WMS.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Tabla v2_mapping_profile
    op.create_table(
        'v2_mapping_profile',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('id_organizacion', sa.String(length=36), nullable=False),
        sa.Column('nombre', sa.String(length=100), nullable=False),
        sa.Column('descripcion', sa.String(length=255), nullable=True),
        sa.Column('mapeo', sa.JSON(), nullable=False),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('fecha_creacion', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('fecha_actualizacion', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['id_organizacion'], ['v2_organizacion.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('id_organizacion', 'nombre', name='uq_v2_mapping_profile_org_nombre'),
    )
    op.create_index('ix_v2_mapping_profile_id_organizacion', 'v2_mapping_profile', ['id_organizacion'], unique=False)

    # 2. Tabla v2_importacion_job
    op.create_table(
        'v2_importacion_job',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('id_organizacion', sa.String(length=36), nullable=False),
        sa.Column('id_mapping_profile', sa.String(length=36), nullable=True),
        sa.Column('id_usuario', sa.String(length=36), nullable=False),
        sa.Column('nombre_archivo', sa.String(length=255), nullable=False),
        sa.Column('tipo_fuente', sa.String(length=20), nullable=False),
        sa.Column('estado', sa.String(length=20), nullable=False, server_default='completado'),
        sa.Column('total_registros', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('registros_validos', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('registros_inconsistentes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('fecha_inicio', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('fecha_fin', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resumen', sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(['id_organizacion'], ['v2_organizacion.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['id_mapping_profile'], ['v2_mapping_profile.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['id_usuario'], ['usuario.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_v2_importacion_job_id_organizacion', 'v2_importacion_job', ['id_organizacion'], unique=False)

    # 3. Tabla v2_inconsistencia
    op.create_table(
        'v2_inconsistencia',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('id_organizacion', sa.String(length=36), nullable=False),
        sa.Column('id_importacion_job', sa.String(length=36), nullable=False),
        sa.Column('fila_origen', sa.Integer(), nullable=False),
        sa.Column('tipo_inconsistencia', sa.String(length=50), nullable=False),
        sa.Column('motivo', sa.String(length=500), nullable=False),
        sa.Column('codigo_ubicacion', sa.String(length=50), nullable=True),
        sa.Column('codigo_item', sa.String(length=50), nullable=True),
        sa.Column('numero_lote', sa.String(length=50), nullable=True),
        sa.Column('cantidad_externa', sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column('datos_crudos', sa.JSON(), nullable=False),
        sa.Column('resuelto', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('fecha_deteccion', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['id_organizacion'], ['v2_organizacion.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['id_importacion_job'], ['v2_importacion_job.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_v2_inconsistencia_id_organizacion', 'v2_inconsistencia', ['id_organizacion'], unique=False)
    op.create_index('ix_v2_inconsistencia_id_importacion_job', 'v2_inconsistencia', ['id_importacion_job'], unique=False)


def downgrade() -> None:
    op.drop_table('v2_inconsistencia')
    op.drop_table('v2_importacion_job')
    op.drop_table('v2_mapping_profile')
