import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base
from app.models.v2.types import JSONDocument


class Lote(Base):
    __tablename__ = "v2_lote"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    id_organizacion = Column(String(36), ForeignKey("v2_organizacion.id", ondelete="CASCADE"), nullable=False, index=True)
    id_item = Column(String(36), ForeignKey("v2_item.id", ondelete="CASCADE"), nullable=False, index=True)
    numero_lote = Column(String(100), nullable=False)
    fecha_fabricacion = Column(DateTime(timezone=True), nullable=True)
    fecha_vencimiento = Column(DateTime(timezone=True), nullable=True, index=True)
    atributos = Column(JSONDocument, default=dict, nullable=False)
    estado = Column(String(30), default="activo", nullable=False)
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("id_item", "numero_lote", name="uq_lote_item_numero"),
    )

    # Relaciones
    item = relationship("Item", back_populates="lotes")
    saldos = relationship("SaldoStock", back_populates="lote", cascade="all, delete-orphan")
