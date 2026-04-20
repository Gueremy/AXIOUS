# app/models/log_auditoria.py
import uuid
import datetime
from sqlalchemy import String, DateTime, JSON, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class LogAuditoria(Base):
    __tablename__ = "log_auditoria"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    id_usuario: Mapped[str] = mapped_column(String, ForeignKey("usuario.id"), nullable=False, index=True)
    accion: Mapped[str] = mapped_column(String, nullable=False) # e.g., "CREAR_CONTAINER", "ACTUALIZAR_SEDE"
    entidad_afectada: Mapped[str] = mapped_column(String, nullable=False) # e.g., "container", "sede"
    id_entidad: Mapped[str] = mapped_column(String, nullable=False, index=True) # ID of the modified entity
    detalles: Mapped[dict] = mapped_column(JSON, nullable=True) # Contains before/after or payload
    fecha_hora: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
        index=True
    )

    # Relación para auditoría (Opcional si queremos cargar el objeto usuario)
    usuario = relationship("Usuario", lazy="raise")
