import uuid
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base
from app.models.v2.types import JSONDocument


class Sitio(Base):
    __tablename__ = "v2_sitio"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    id_organizacion = Column(String(36), ForeignKey("v2_organizacion.id", ondelete="CASCADE"), nullable=False, index=True)
    codigo = Column(String(50), nullable=False)
    nombre = Column(String(150), nullable=False)
    tipo = Column(String(50), nullable=False)  # e.g., 'planta', 'bodega', 'centro_flotante', 'patio'
    descripcion = Column(String(300), nullable=True)
    ubicacion_geografica = Column(String(200), nullable=True)
    atributos = Column(JSONDocument, default=dict, nullable=False)
    activo = Column(Boolean, default=True, nullable=False)
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("id_organizacion", "codigo", name="uq_sitio_org_codigo"),
    )

    # Relaciones
    organizacion = relationship("Organizacion", back_populates="sitios")
    zonas = relationship("Zona", back_populates="sitio", cascade="all, delete-orphan")
