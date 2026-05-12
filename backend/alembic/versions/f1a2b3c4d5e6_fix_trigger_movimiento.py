"""fix_trigger_movimiento

Revision ID: f1a2b3c4d5e6
Revises: e5f9a2b3c1d4
Create Date: 2026-05-12 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op

revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'e5f9a2b3c1d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_movimiento_update()
        RETURNS trigger AS $$
        BEGIN
            -- FIX: Permitir transicion de estado (pendiente -> aprobado/rechazado)
            IF OLD.estado = 'pendiente' AND (NEW.estado = 'aprobado' OR NEW.estado = 'rechazado') THEN
                RETURN NEW;
            END IF;

            RAISE EXCEPTION
                'Los movimientos son inmutables (SERNAPESCA). '
                'Para rectificar, crea un movimiento de tipo=correccion '
                'con id_movimiento_original apuntando al registro erroneo.';
        END;
        $$ LANGUAGE plpgsql;
    """)

def downgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_movimiento_update()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION
                'Los movimientos son inmutables (SERNAPESCA). '
                'Para rectificar, crea un movimiento de tipo=correccion '
                'con id_movimiento_original apuntando al registro erroneo.';
        END;
        $$ LANGUAGE plpgsql;
    """)
