"""
app/models/v2/regla_ubicacion.py
Reglas dinámicas y configurables de ubicación (Fase 1B).
Permite configurar por organización, sitio, zona o ubicación:
- Capacidad y ocupación
- Prohibición / permisión de mezcla de lotes
- Categorías e ítems permitidos
- Reglas personalizadas evaluadas centralmente
"""
import uuid
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class ReglaUbicacion(Base):
    __tablename__ = "v2_regla_ubicacion"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    id_organizacion = Column(String(36), ForeignKey("v2_organizacion.id", ondelete="CASCADE"), nullable=False, index=True)
    id_sitio = Column(String(36), ForeignKey("v2_sitio.id", ondelete="CASCADE"), nullable=True, index=True)
    id_zona = Column(String(36), ForeignKey("v2_zona.id", ondelete="CASCADE"), nullable=True, index=True)
    id_ubicacion = Column(String(36), ForeignKey("v2_ubicacion.id", ondelete="CASCADE"), nullable=True, index=True)
    codigo = Column(String(50), nullable=False)  # e.g., 'NO_MEZCLA_LOTES', 'SOLO_MATERIA_PRIMA'
    nombre = Column(String(100), nullable=False)
    tipo_regla = Column(String(50), nullable=False)  # 'mezcla_lotes', 'categorias_permitidas', 'items_permitidos', 'capacidad'
    configuracion = Column(JSON, default=dict, nullable=False)
    activo = Column(Boolean, default=True, nullable=False)
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
