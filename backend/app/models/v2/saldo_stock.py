import uuid
from sqlalchemy import (
    Column, String, DateTime, ForeignKey,
    Numeric, UniqueConstraint, CheckConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class SaldoStock(Base):
    __tablename__ = "v2_saldo_stock"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    id_organizacion = Column(String(36), ForeignKey("v2_organizacion.id", ondelete="CASCADE"), nullable=False, index=True)
    id_ubicacion = Column(String(36), ForeignKey("v2_ubicacion.id", ondelete="CASCADE"), nullable=False, index=True)
    id_item = Column(String(36), ForeignKey("v2_item.id", ondelete="CASCADE"), nullable=False, index=True)
    id_lote = Column(String(36), ForeignKey("v2_lote.id", ondelete="CASCADE"), nullable=True, index=True)
    cantidad = Column(Numeric(12, 4), default=0.0, nullable=False)
    unidad_medida = Column(String(20), nullable=False)
    fecha_actualizacion = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("id_ubicacion", "id_item", "id_lote", name="uq_saldo_ubicacion_item_lote"),
        CheckConstraint("cantidad >= 0", name="chk_saldo_cantidad_no_negativa"),
    )

    # Relaciones
    ubicacion = relationship("Ubicacion", back_populates="saldos")
    item = relationship("Item", back_populates="saldos")
    lote = relationship("Lote", back_populates="saldos")
