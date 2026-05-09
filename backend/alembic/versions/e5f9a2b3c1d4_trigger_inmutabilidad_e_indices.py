"""trigger_inmutabilidad_e_indices

Revision ID: e5f9a2b3c1d4
Revises: d367941070ea
Create Date: 2026-05-08 00:00:00.000000

AXI-7 + AXI-8
- Trigger PostgreSQL que bloquea UPDATE y DELETE en tabla movimiento (SERNAPESCA)
- 7 indices de performance para render 3D, trazabilidad y alertas
"""
from typing import Sequence, Union
from alembic import op


revision: str = 'e5f9a2b3c1d4'
down_revision: Union[str, Sequence[str], None] = 'd367941070ea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── AXI-7: Trigger inmutabilidad SERNAPESCA ───────────────────────────────
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

    op.execute("""
        CREATE TRIGGER trg_movimiento_immutable
        BEFORE UPDATE OR DELETE ON movimiento
        FOR EACH ROW EXECUTE FUNCTION prevent_movimiento_update();
    """)

    # ── AXI-8: Indices de performance ────────────────────────────────────────

    # Trazabilidad SERNAPESCA — busqueda exacta y full-text por lote
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_movimiento_numero_lote
            ON movimiento (numero_lote);
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_movimiento_lote_gin
            ON movimiento USING gin(to_tsvector('spanish', numero_lote));
    """)

    # FEFO — vencimientos proximos (solo aprobados)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_movimiento_vencimiento
            ON movimiento (fecha_vencimiento ASC) WHERE estado = 'aprobado';
    """)

    # Historial por container ordenado por fecha
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_movimiento_container_fecha
            ON movimiento (id_container, fecha_hora DESC);
    """)

    # Render 3D — containers por galpon y estado
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_container_galpon_estado
            ON container (id_galpon, estado);
    """)

    # Dashboard jefe de bodega — pendientes recientes
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_movimiento_pendiente
            ON movimiento (estado, fecha_hora DESC) WHERE estado = 'pendiente';
    """)

    # Dashboard alertas activas
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_alerta_activa
            ON alerta (id_container, estado) WHERE estado = 'activa';
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_movimiento_immutable ON movimiento;")
    op.execute("DROP FUNCTION IF EXISTS prevent_movimiento_update();")

    op.execute("DROP INDEX IF EXISTS idx_movimiento_numero_lote;")
    op.execute("DROP INDEX IF EXISTS idx_movimiento_lote_gin;")
    op.execute("DROP INDEX IF EXISTS idx_movimiento_vencimiento;")
    op.execute("DROP INDEX IF EXISTS idx_movimiento_container_fecha;")
    op.execute("DROP INDEX IF EXISTS idx_container_galpon_estado;")
    op.execute("DROP INDEX IF EXISTS idx_movimiento_pendiente;")
    op.execute("DROP INDEX IF EXISTS idx_alerta_activa;")
