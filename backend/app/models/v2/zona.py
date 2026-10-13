import uuid
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base
from app.models.v2.types import JSONDocument


class Zona(Base):
    __tablename__ = "v2_zona"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    id_organizacion = Column(String(36), ForeignKey("v2_organizacion.id", ondelete="CASCADE"), nullable=False, index=True)
    id_sitio = Column(String(36), ForeignKey("v2_sitio.id", ondelete="CASCADE"), nullable=False, index=True)
    id_zona_padre = Column(String(36), ForeignKey("v2_zona.id", ondelete="CASCADE"), nullable=True, index=True)
    codigo = Column(String(50), nullable=False)
    nombre = Column(String(150), nullable=False)
    tipo = Column(String(50), nullable=False)  # e.g., 'galpon', 'sector', 'pasillo', 'patio'
    layout = Column(JSONDocument, default=dict, nullable=False)  # coordenadas 2D/3D, dimensiones
    atributos = Column(JSONDocument, default=dict, nullable=False)
    activo = Column(Boolean, default=True, nullable=False)
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("id_sitio", "codigo", name="uq_zona_sitio_codigo"),
    )

    # Relaciones
    sitio = relationship("Sitio", back_populates="zonas")
    padre = relationship("Zona", remote_side=[id], back_populates="hijos")
    hijos = relationship("Zona", back_populates="padre", cascade="all, delete-orphan")
    ubicaciones = relationship("Ubicacion", back_populates="zona", cascade="all, delete-orphan")
