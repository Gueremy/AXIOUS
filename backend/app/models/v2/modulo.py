import uuid
from sqlalchemy import (
    Column,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    JSON,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class ModuloOrganizacion(Base):
    """
    Registro y estado de activación de módulos y feature flags por organización (Fase 2C).
    Permite encender o apagar capacidades (offline_sync, pack_salmonero, importacion, fefo)
    de forma independiente por cada tenant.
    """
    __tablename__ = "v2_organizacion_modulo"
    __table_args__ = (
        UniqueConstraint("id_organizacion", "id_modulo", name="uq_v2_org_modulo"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    id_organizacion = Column(String(36), ForeignKey("v2_organizacion.id", ondelete="CASCADE"), nullable=False, index=True)
    id_modulo = Column(String(50), nullable=False, index=True)  # 'offline_sync', 'importacion', 'pack_salmonero', 'fefo'
    habilitado = Column(Boolean, nullable=False, default=True)
    configuracion = Column(JSON, nullable=False, default=dict)
    fecha_activacion = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    organizacion = relationship("Organizacion", lazy="raise")
