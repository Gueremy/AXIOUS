import uuid
from sqlalchemy import (
    Column, String, Boolean, DateTime, ForeignKey,
    Numeric, JSON, UniqueConstraint, CheckConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base
from app.models.v2.types import JSONDocument


class Ubicacion(Base):
    __tablename__ = "v2_ubicacion"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    id_organizacion = Column(String(36), ForeignKey("v2_organizacion.id", ondelete="CASCADE"), nullable=False, index=True)
    id_zona = Column(String(36), ForeignKey("v2_zona.id", ondelete="CASCADE"), nullable=False, index=True)
    codigo = Column(String(50), nullable=False)
    capacidad_maxima = Column(Numeric(12, 4), nullable=False)
    unidad_capacidad = Column(String(20), nullable=False)
    ocupacion_actual = Column(Numeric(12, 4), default=0.0, nullable=False)
    permite_mezcla_lotes = Column(Boolean, default=True, nullable=False)
    estado = Column(String(30), default="disponible", nullable=False)  # configurable por org
    layout = Column(JSONDocument, default=dict, nullable=False)  # posicionamiento espacial
    atributos = Column(JSONDocument, default=dict, nullable=False)
    activo = Column(Boolean, default=True, nullable=False)
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("id_zona", "codigo", name="uq_ubicacion_zona_codigo"),
        CheckConstraint("capacidad_maxima >= 0", name="chk_ubicacion_capacidad_positiva"),
    )

    # Relaciones
    zona = relationship("Zona", back_populates="ubicaciones")
    saldos = relationship("SaldoStock", back_populates="ubicacion", cascade="all, delete-orphan")
