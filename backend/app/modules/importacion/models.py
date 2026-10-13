import uuid
from sqlalchemy import (
    Column,
    String,
    Integer,
    Numeric,
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


class MappingProfile(Base):
    """
    Perfil de mapeo de columnas configurable por organización (Fase 1E).
    Permite mapear encabezados de sistemas ERP/WMS externos (SAP, Oracle, Excel)
    a los campos canónicos de SalmoTrack v2.
    """
    __tablename__ = "v2_mapping_profile"
    __table_args__ = (
        UniqueConstraint("id_organizacion", "nombre", name="uq_v2_mapping_profile_org_nombre"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    id_organizacion = Column(String(36), ForeignKey("v2_organizacion.id", ondelete="CASCADE"), nullable=False, index=True)
    nombre = Column(String(100), nullable=False)
    descripcion = Column(String(255), nullable=True)
    mapeo = Column(JSONDocument, nullable=False)  # ej: {"codigo_ubicacion": "POS", "codigo_item": "SKU", "cantidad": "QTY", "numero_lote": "LOT"}
    activo = Column(Boolean, nullable=False, default=True)
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    fecha_actualizacion = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    organizacion = relationship("Organizacion", lazy="raise")
    jobs = relationship("ImportacionJob", back_populates="mapping_profile", lazy="raise")


class ImportacionJob(Base):
    """
    Registro histórico de una ejecución de importación y conciliación.
    """
    __tablename__ = "v2_importacion_job"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    id_organizacion = Column(String(36), ForeignKey("v2_organizacion.id", ondelete="CASCADE"), nullable=False, index=True)
    id_mapping_profile = Column(String(36), ForeignKey("v2_mapping_profile.id", ondelete="SET NULL"), nullable=True)
    id_usuario = Column(String(36), ForeignKey("usuario.id", ondelete="RESTRICT"), nullable=False)
    nombre_archivo = Column(String(255), nullable=False)
    tipo_fuente = Column(String(20), nullable=False)  # 'csv', 'excel', 'api'
    estado = Column(String(20), nullable=False, default="completado")  # 'pendiente', 'procesando', 'completado', 'fallido'
    total_registros = Column(Integer, nullable=False, default=0)
    registros_validos = Column(Integer, nullable=False, default=0)
    registros_inconsistentes = Column(Integer, nullable=False, default=0)
    fecha_inicio = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    fecha_fin = Column(DateTime(timezone=True), nullable=True)
    resumen = Column(JSONDocument, nullable=False, default=dict)

    organizacion = relationship("Organizacion", lazy="raise")
    mapping_profile = relationship("MappingProfile", back_populates="jobs", lazy="raise")
    usuario = relationship("Usuario", lazy="raise")
    inconsistencias = relationship("Inconsistencia", back_populates="job", cascade="all, delete-orphan", lazy="raise")


class Inconsistencia(Base):
    """
    Inconsistencia detectada durante el proceso de conciliación con el sistema externo.
    Permite auditar sobrecapacidad, ubicaciones inexistentes, mezclas prohibidas y datos faltantes.
    """
    __tablename__ = "v2_inconsistencia"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    id_organizacion = Column(String(36), ForeignKey("v2_organizacion.id", ondelete="CASCADE"), nullable=False, index=True)
    id_importacion_job = Column(String(36), ForeignKey("v2_importacion_job.id", ondelete="CASCADE"), nullable=False, index=True)
    id_ubicacion = Column(String(36), ForeignKey("v2_ubicacion.id", ondelete="SET NULL"), nullable=True, index=True)
    fila_origen = Column(Integer, nullable=False)
    tipo_inconsistencia = Column(String(50), nullable=False)  # 'ubicacion_inexistente', 'sobrecapacidad', 'mezcla_lotes', 'item_incompatible', 'datos_incompletos'
    motivo = Column(String(500), nullable=False)
    codigo_ubicacion = Column(String(50), nullable=True)
    codigo_item = Column(String(50), nullable=True)
    numero_lote = Column(String(50), nullable=True)
    cantidad_externa = Column(Numeric(precision=12, scale=4), nullable=True)
    datos_crudos = Column(JSONDocument, nullable=False, default=dict)
    resuelto = Column(Boolean, nullable=False, default=False)
    fecha_deteccion = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    organizacion = relationship("Organizacion", lazy="raise")
    job = relationship("ImportacionJob", back_populates="inconsistencias", lazy="raise")
