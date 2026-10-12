"""add_v2_rbac_and_user_org

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-10-12 15:20:00.000000

Fase 0C: Agrega RBAC dinámico y vincula usuarios con organizaciones:
- v2_rol
- v2_permiso
- v2_rol_permiso
- v2_usuario_sitio
- usuario.id_organizacion
- usuario.id_rol_v2
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. v2_rol
    op.create_table(
        'v2_rol',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('id_organizacion', sa.String(length=36), nullable=False),
        sa.Column('codigo', sa.String(length=50), nullable=False),
        sa.Column('nombre', sa.String(length=100), nullable=False),
        sa.Column('descripcion', sa.String(length=250), nullable=True),
        sa.Column('es_sistema', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('fecha_creacion', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['id_organizacion'], ['v2_organizacion.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('id_organizacion', 'codigo', name='uq_rol_org_codigo'),
    )
    op.create_index('ix_v2_rol_id_organizacion', 'v2_rol', ['id_organizacion'], unique=False)

    # 2. v2_permiso
    op.create_table(
        'v2_permiso',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('codigo', sa.String(length=100), nullable=False),
        sa.Column('modulo', sa.String(length=50), nullable=False),
        sa.Column('descripcion', sa.String(length=200), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_v2_permiso_codigo', 'v2_permiso', ['codigo'], unique=True)

    # 3. v2_rol_permiso
    op.create_table(
        'v2_rol_permiso',
        sa.Column('id_rol', sa.String(length=36), nullable=False),
        sa.Column('id_permiso', sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(['id_permiso'], ['v2_permiso.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['id_rol'], ['v2_rol.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id_rol', 'id_permiso'),
    )

    # 4. v2_usuario_sitio
    op.create_table(
        'v2_usuario_sitio',
        sa.Column('id_usuario', sa.String(length=36), nullable=False),
        sa.Column('id_sitio', sa.String(length=36), nullable=False),
        sa.Column('fecha_asignacion', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['id_sitio'], ['v2_sitio.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['id_usuario'], ['usuario.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id_usuario', 'id_sitio'),
    )

    # 5. Agregar id_organizacion e id_rol_v2 a usuario
    op.add_column('usuario', sa.Column('id_organizacion', sa.String(length=36), nullable=True))
    op.add_column('usuario', sa.Column('id_rol_v2', sa.String(length=36), nullable=True))
    op.create_foreign_key('fk_usuario_id_organizacion', 'usuario', 'v2_organizacion', ['id_organizacion'], ['id'])
    op.create_foreign_key('fk_usuario_id_rol_v2', 'usuario', 'v2_rol', ['id_rol_v2'], ['id'])
    op.create_index('ix_usuario_id_organizacion', 'usuario', ['id_organizacion'], unique=False)
    op.create_index('ix_usuario_id_rol_v2', 'usuario', ['id_rol_v2'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_usuario_id_rol_v2', table_name='usuario')
    op.drop_index('ix_usuario_id_organizacion', table_name='usuario')
    op.drop_constraint('fk_usuario_id_rol_v2', 'usuario', type_='foreignkey')
    op.drop_constraint('fk_usuario_id_organizacion', 'usuario', type_='foreignkey')
    op.drop_column('usuario', 'id_rol_v2')
    op.drop_column('usuario', 'id_organizacion')
    op.drop_table('v2_usuario_sitio')
    op.drop_table('v2_rol_permiso')
    op.drop_table('v2_permiso')
    op.drop_table('v2_rol')
