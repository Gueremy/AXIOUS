import uuid
from sqlalchemy import Column, String, Integer, Enum, DateTime, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class Sede(Base):
    __tablename__ = "sede"

    id = Column(String(36), primary_key=True,
                default=lambda: str(uuid.uuid4()))
    nombre = Column(String(100), nullable=False)
    tipo = Column(
        Enum("ponton", "planta", "bodega", name="tipo_sede"),
        nullable=False
    )
    ubicacion   = Column(String(200))
    latitud     = Column(Numeric(9, 6))
    longitud    = Column(Numeric(9, 6))
    capacidad_total = Column(Integer)
    estado = Column(
        Enum("activo", "inactivo", name="estado_sede"),
        default="activo"
    )
    fecha_creacion = Column(DateTime(timezone=True),
                            server_default=func.now())

    # Relaciones
    galpones = relationship("Galpon", back_populates="sede",
                            lazy="raise")
    usuarios = relationship("Usuario", back_populates="sede",
                            lazy="raise")
