"""Clave persistente de idempotencia de eventos de sistemas externos."""
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base


class EventoEntranteRegistrado(Base):
    __tablename__ = "v2_evento_entrante"
    __table_args__ = (UniqueConstraint("id_organizacion", "fuente", "id_evento_externo",
                                      name="uq_v2_evento_entrante_clave"),)

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    id_organizacion = Column(String(36), ForeignKey("v2_organizacion.id", ondelete="CASCADE"), nullable=False, index=True)
    fuente = Column(String(100), nullable=False)
    id_evento_externo = Column(String(150), nullable=False)
    tipo_evento = Column(String(100), nullable=False)
    fecha_recepcion = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
