import uuid
from sqlalchemy import Column, String, Boolean, DateTime, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Organizacion(Base):
    __tablename__ = "v2_organizacion"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    nombre = Column(String(150), nullable=False)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    activo = Column(Boolean, default=True, nullable=False)
    configuracion = Column(JSON, default=dict, nullable=False)
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relaciones
    sitios = relationship("Sitio", back_populates="organizacion", cascade="all, delete-orphan")
    items = relationship("Item", back_populates="organizacion", cascade="all, delete-orphan")
    esquemas = relationship("EsquemaAtributos", back_populates="organizacion", cascade="all, delete-orphan")
