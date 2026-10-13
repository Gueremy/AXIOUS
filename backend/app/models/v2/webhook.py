"""Destinos y entregas durables de webhooks por organización."""
import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base
from app.models.v2.types import JSONDocument


class WebhookDestino(Base):
    __tablename__ = "v2_webhook_destino"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    id_organizacion = Column(String(36), ForeignKey("v2_organizacion.id", ondelete="CASCADE"), nullable=False, index=True)
    url = Column(String(2048), nullable=False)
    secreto_cifrado = Column(String(1024), nullable=False)
    eventos = Column(JSONDocument, nullable=False)
    activo = Column(Boolean, nullable=False, default=True)
    fecha_creacion = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (UniqueConstraint("id_organizacion", "url", name="uq_webhook_destino_org_url"),)


class WebhookEntrega(Base):
    __tablename__ = "v2_webhook_entrega"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    id_organizacion = Column(String(36), ForeignKey("v2_organizacion.id", ondelete="CASCADE"), nullable=False, index=True)
    id_destino = Column(String(36), ForeignKey("v2_webhook_destino.id", ondelete="CASCADE"), nullable=False, index=True)
    tipo_evento = Column(String(100), nullable=False)
    id_evento = Column(String(100), nullable=False)
    payload = Column(JSONDocument, nullable=False)
    estado = Column(String(20), nullable=False, default="pendiente")
    intentos = Column(Integer, nullable=False, default=0)
    proximo_intento = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    fecha_creacion = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    fecha_envio = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("id_destino", "tipo_evento", "id_evento", name="uq_webhook_entrega_evento"),
        Index("ix_v2_webhook_entrega_due", "estado", "proximo_intento"),
    )
