"""
app/models/refresh_token.py
Tabla para almacenar refresh tokens (Opción B — logout real).
Permite revocar sesiones activas sin esperar expiración del JWT.
"""
import uuid
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class RefreshToken(Base):
    __tablename__ = "refresh_token"

    id         = Column(String(36), primary_key=True,
                        default=lambda: str(uuid.uuid4()))
    token      = Column(String(512), nullable=False, unique=True, index=True)
    id_usuario = Column(String(36), ForeignKey("usuario.id"), nullable=False)
    revocado   = Column(Boolean, default=False, nullable=False)
    fecha_creacion = Column(DateTime(timezone=True),
                            server_default=func.now())
    fecha_expiracion = Column(DateTime(timezone=True), nullable=False)

    usuario = relationship("Usuario", lazy="raise")
