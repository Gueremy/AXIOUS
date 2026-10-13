"""
app/models/v2/movimiento.py
Movimiento confirmado inmutable (v2_movimiento).
Representa el libro diario contable/físico de existencias.
Una vez confirmado, jamás se modifica ni se elimina; los errores se compensan
mediante un nuevo movimiento referenciando id_movimiento_original.
"""
import uuid
from sqlalchemy import (
    Column, String, DateTime, ForeignKey,
    Numeric, JSON, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base
from app.models.v2.types import JSONDocument


class MovimientoV2(Base):
    __tablename__ = "v2_movimiento"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    id_organizacion = Column(String(36), ForeignKey("v2_organizacion.id", ondelete="CASCADE"), nullable=False, index=True)
    id_solicitud = Column(String(36), ForeignKey("v2_solicitud_movimiento.id", ondelete="SET NULL"), nullable=True, index=True)
    id_tipo_movimiento = Column(String(36), ForeignKey("v2_tipo_movimiento.id", ondelete="RESTRICT"), nullable=False, index=True)
    id_movimiento_original = Column(String(36), ForeignKey("v2_movimiento.id", ondelete="RESTRICT"), nullable=True, index=True)
    id_item = Column(String(36), ForeignKey("v2_item.id", ondelete="RESTRICT"), nullable=False, index=True)
    id_lote = Column(String(36), ForeignKey("v2_lote.id", ondelete="RESTRICT"), nullable=True, index=True)
    id_ubicacion_origen = Column(String(36), ForeignKey("v2_ubicacion.id", ondelete="RESTRICT"), nullable=True, index=True)
    id_ubicacion_destino = Column(String(36), ForeignKey("v2_ubicacion.id", ondelete="RESTRICT"), nullable=True, index=True)
    id_usuario = Column(String(36), ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False, index=True)
    id_usuario_aprobador = Column(String(36), ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=True, index=True)
    cantidad = Column(Numeric(12, 4), nullable=False)
    unidad_medida = Column(String(20), nullable=False)
    efecto_stock = Column(String(20), nullable=False)  # 'entrada', 'salida', 'traslado', 'sin_efecto'
    uuid_local = Column(String(36), nullable=True)  # Idempotencia de sincronización offline
    atributos = Column(JSONDocument, default=dict, nullable=False)
    fecha_hora = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    observaciones = Column(String(300), nullable=True)

    __table_args__ = (
        UniqueConstraint("id_organizacion", "uuid_local", name="uq_mov_v2_org_uuid_local"),
        UniqueConstraint("id_solicitud", name="uq_mov_v2_solicitud"),
    )

    # Relaciones
    tipo_movimiento = relationship("TipoMovimiento")
    item = relationship("Item")
    lote = relationship("Lote")
    ubicacion_origen = relationship("Ubicacion", foreign_keys=[id_ubicacion_origen])
    ubicacion_destino = relationship("Ubicacion", foreign_keys=[id_ubicacion_destino])
    usuario = relationship("Usuario", foreign_keys=[id_usuario])
    usuario_aprobador = relationship("Usuario", foreign_keys=[id_usuario_aprobador])
    movimiento_original = relationship("MovimientoV2", remote_side=[id])
