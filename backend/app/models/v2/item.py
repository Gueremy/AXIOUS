import uuid
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Item(Base):
    __tablename__ = "v2_item"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    id_organizacion = Column(String(36), ForeignKey("v2_organizacion.id", ondelete="CASCADE"), nullable=False, index=True)
    codigo = Column(String(50), nullable=False)
    nombre = Column(String(150), nullable=False)
    categoria = Column(String(50), nullable=False)
    unidad_medida = Column(String(20), nullable=False)
    atributos = Column(JSON, default=dict, nullable=False)
    activo = Column(Boolean, default=True, nullable=False)
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("id_organizacion", "codigo", name="uq_item_org_codigo"),
    )

    # Relaciones
    organizacion = relationship("Organizacion", back_populates="items")
    lotes = relationship("Lote", back_populates="item", cascade="all, delete-orphan")
    saldos = relationship("SaldoStock", back_populates="item", cascade="all, delete-orphan")
