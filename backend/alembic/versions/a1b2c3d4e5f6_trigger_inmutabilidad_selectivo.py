"""trigger_inmutabilidad_selectivo

Revision ID: a1b2c3d4e5f6
Revises: f1a2b3c4d5e6
Create Date: 2026-05-12 04:20:00.000000

Reemplaza el trigger de inmutabilidad por uno selectivo que:
- PERMITE cambiar: estado, id_usuario_aprobador, fecha_aprobacion, motivo_rechazo
  (campos del flujo de aprobación — PATCH /aprobar y PATCH /rechazar)
- BLOQUEA cambiar: cantidad, tipo, id_container, id_producto, numero_lote,
  fecha_vencimiento, nombre_proveedor, num_guia_despacho, registro_sanitario,
  temperatura_almacen, origen
  (campos críticos de trazabilidad SERNAPESCA — NUNCA deben modificarse)

El trigger anterior (f1a2b3c4d5e6) permitía cualquier transición
pendiente→aprobado/rechazado pero no protegía los campos críticos.
Este trigger es más preciso: protege por campo, no por transición de estado.
"""
from typing import Sequence, Union
from alembic import op


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_movimiento_update()
        RETURNS trigger AS $$
        BEGIN
            -- ── Campos SERNAPESCA críticos — NUNCA modificables ──────────────
            -- Cualquier intento de cambiar estos campos lanza excepción,
            -- sin importar quién lo intente o cuál sea el estado actual.
            IF (
                NEW.cantidad            IS DISTINCT FROM OLD.cantidad            OR
                NEW.tipo                IS DISTINCT FROM OLD.tipo                OR
                NEW.id_container        IS DISTINCT FROM OLD.id_container        OR
                NEW.id_producto         IS DISTINCT FROM OLD.id_producto         OR
                NEW.numero_lote         IS DISTINCT FROM OLD.numero_lote         OR
                NEW.fecha_vencimiento   IS DISTINCT FROM OLD.fecha_vencimiento   OR
                NEW.nombre_proveedor    IS DISTINCT FROM OLD.nombre_proveedor    OR
                NEW.num_guia_despacho   IS DISTINCT FROM OLD.num_guia_despacho   OR
                NEW.registro_sanitario  IS DISTINCT FROM OLD.registro_sanitario  OR
                NEW.temperatura_almacen IS DISTINCT FROM OLD.temperatura_almacen OR
                NEW.origen              IS DISTINCT FROM OLD.origen
            ) THEN
                RAISE EXCEPTION
                    'Los movimientos son inmutables (SERNAPESCA). '
                    'No se puede modificar: cantidad, tipo, id_container, id_producto, '
                    'numero_lote, fecha_vencimiento, nombre_proveedor, num_guia_despacho, '
                    'registro_sanitario, temperatura_almacen u origen. '
                    'Para rectificar usa tipo=correccion con id_movimiento_original.';
            END IF;

            -- ── Campos permitidos del flujo de aprobación ─────────────────
            -- estado, id_usuario_aprobador, fecha_aprobacion, motivo_rechazo
            -- pueden cambiar (son actualizados por PATCH /aprobar y PATCH /rechazar)
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    # Vuelve al trigger anterior (f1a2b3c4d5e6): permite pendiente→aprobado/rechazado
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_movimiento_update()
        RETURNS trigger AS $$
        BEGIN
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
