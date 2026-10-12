"""
app/models/v2/solicitud_movimiento.py
Solicitud previa de movimiento de stock.
Entidad mutable que registra intenciones operativas y su ciclo de vida (pendiente, aprobada, rechazada).
Las solicitudes pendientes no descuentan ni reservan stock inicialmente.
"""
import uuid
from sqlalchemy import (
    Column, String, DateTime, ForeignKey,
    Numeric, JSON, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class SolicitudMovimiento(Base):
    __tablename__ = "v2_solicitud_movimiento"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    id_organizacion = Column(String(36), ForeignKey("v2_organizacion.id", ondelete="CASCADE"), nullable=False, index=True)
    id_tipo_movimiento = Column(String(36), ForeignKey("v2_tipo_movimiento.id", ondelete="RESTRICT"), nullable=False, index=True)
    id_item = Column(String(36), ForeignKey("v2_item.id", ondelete="RESTRICT"), nullable=False, index=True)
    id_lote = Column(String(36), ForeignKey("v2_lote.id", ondelete="RESTRICT"), nullable=True, index=True)
    id_ubicacion_origen = Column(String(36), ForeignKey("v2_ubicacion.id", ondelete="RESTRICT"), nullable=True, index=True)
    id_ubicacion_destino = Column(String(36), ForeignKey("v2_ubicacion.id", ondelete="RESTRICT"), nullable=True, index=True)
    id_usuario_solicitante = Column(String(36), ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False, index=True)
    id_usuario_aprobador = Column(String(36), ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=True, index=True)
    cantidad = Column(Numeric(12, 4), nullable=False)
    unidad_medida = Column(String(20), nullable=False)
    estado = Column(String(20), default="pendiente", nullable=False)  # 'pendiente', 'aprobada', 'rechazada', 'cancelada'
    motivo_rechazo = Column(String(300), nullable=True)
    observaciones = Column(String(300), nullable=True)
    uuid_local = Column(String(36), nullable=True)  # Idempotencia de dispositivos cliente
    atributos = Column(JSON, default=dict, nullable=False)
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    fecha_resolucion = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("id_organizacion", "uuid_local", name="uq_solicitud_org_uuid_local"),
    )

    # Relaciones
    tipo_movimiento = relationship("TipoMovimiento")
    item = relationship("Item")
    lote = relationship("Lote")
    ubicacion_origen = relationship("Ubicacion", foreign_keys=[id_ubicacion_origen])
    ubicacion_destino = relationship("Ubicacion", foreign_keys=[id_ubicacion_destino])
    usuario_solicitante = relationship("Usuario", foreign_keys=[id_usuario_solicitante])
    usuario_aprobador = relationship("Usuario", foreign_keys=[id_usuario_aprobador])
