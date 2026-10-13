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
from app.models.v2.types import JSONDocument


class ReglaAlertaV2(Base):
    """
    Reglas configurables de alertas por organización (Fase 1D).
    Permite ajustar umbrales (ej. % capacidad, días de vencimiento) y severidades
    sin modificar el código fuente.
    """
    __tablename__ = "v2_regla_alerta"
    __table_args__ = (
        UniqueConstraint("id_organizacion", "codigo", name="uq_v2_regla_alerta_org_codigo"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    id_organizacion = Column(String(36), ForeignKey("v2_organizacion.id", ondelete="CASCADE"), nullable=False, index=True)
    codigo = Column(String(50), nullable=False)  # ej: 'capacidad_critica', 'vencimiento_7_dias'
    nombre = Column(String(100), nullable=False)
    tipo = Column(String(50), nullable=False)    # 'capacidad', 'vencimiento', 'stock', 'inactividad', 'conciliacion'
    configuracion = Column(JSONDocument, nullable=False, default=dict)  # ej: {"umbral_porcentaje": 90.0}
    severidad = Column(String(20), nullable=False, default="aviso")  # 'critica', 'aviso', 'informativa'
    habilitada = Column(Boolean, nullable=False, default=True)
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    fecha_actualizacion = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    organizacion = relationship("Organizacion", lazy="raise")
    alertas = relationship("AlertaV2", back_populates="regla", lazy="raise")


class AlertaV2(Base):
    """
    Alertas generadas en el dominio genérico v2.
    Aisladas por organización y referenciando ubicación, ítem o lote de forma opcional.
    """
    __tablename__ = "v2_alerta"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    id_organizacion = Column(String(36), ForeignKey("v2_organizacion.id", ondelete="CASCADE"), nullable=False, index=True)
    id_regla = Column(String(36), ForeignKey("v2_regla_alerta.id", ondelete="SET NULL"), nullable=True, index=True)
    id_sitio = Column(String(36), ForeignKey("v2_sitio.id", ondelete="SET NULL"), nullable=True, index=True)
    id_ubicacion = Column(String(36), ForeignKey("v2_ubicacion.id", ondelete="SET NULL"), nullable=True, index=True)
    id_item = Column(String(36), ForeignKey("v2_item.id", ondelete="SET NULL"), nullable=True, index=True)
    id_lote = Column(String(36), ForeignKey("v2_lote.id", ondelete="SET NULL"), nullable=True, index=True)

    tipo = Column(String(50), nullable=False)       # ej: 'capacidad_critica', 'vencimiento'
    severidad = Column(String(20), nullable=False)  # 'critica', 'aviso', 'informativa'
    titulo = Column(String(150), nullable=False)
    descripcion = Column(String(500), nullable=False)
    estado = Column(String(20), nullable=False, default="activa")  # 'activa', 'revisada', 'resuelta'

    id_usuario_revision = Column(String(36), ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True)
    fecha_generacion = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    fecha_revision = Column(DateTime(timezone=True), nullable=True)
    fecha_resolucion = Column(DateTime(timezone=True), nullable=True)
    metadatos = Column(JSONDocument, nullable=False, default=dict)

    regla = relationship("ReglaAlertaV2", back_populates="alertas", lazy="raise")
    organizacion = relationship("Organizacion", lazy="raise")
    sitio = relationship("Sitio", lazy="raise")
    ubicacion = relationship("Ubicacion", lazy="raise")
    item = relationship("Item", lazy="raise")
    lote = relationship("Lote", lazy="raise")
    usuario_revision = relationship("Usuario", lazy="raise")
