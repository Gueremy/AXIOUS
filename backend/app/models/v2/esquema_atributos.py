import uuid
from sqlalchemy import Column, String, Boolean, DateTime, Integer, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base
from app.models.v2.types import JSONDocument


class EsquemaAtributos(Base):
    __tablename__ = "v2_esquema_atributos"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    id_organizacion = Column(String(36), ForeignKey("v2_organizacion.id", ondelete="CASCADE"), nullable=False, index=True)
    entidad = Column(String(50), nullable=False)  # 'sitio', 'zona', 'ubicacion', 'item', 'lote', 'movimiento'
    nombre = Column(String(100), nullable=False)
    version = Column(Integer, default=1, nullable=False)
    schema_json = Column(JSONDocument, nullable=False)
    activo = Column(Boolean, default=True, nullable=False)
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("id_organizacion", "entidad", "nombre", "version", name="uq_esquema_org_entidad_ver"),
    )

    # Relaciones
    organizacion = relationship("Organizacion", back_populates="esquemas")
