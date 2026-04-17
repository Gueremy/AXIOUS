import uuid
from sqlalchemy import Column, String, Integer, ForeignKey, Enum
from sqlalchemy.orm import relationship
from app.database import Base

class Galpon(Base):
    __tablename__ = "galpon"

    id      = Column(String(36), primary_key=True,
                     default=lambda: str(uuid.uuid4()))
    id_sede = Column(String(36), ForeignKey("sede.id"),
                     nullable=False)
    nombre  = Column(String(100), nullable=False)
    codigo  = Column(String(10),  nullable=False)   # G1, G2...
    filas   = Column(Integer, nullable=False)
    columnas = Column(Integer, nullable=False)
    estado = Column(
        Enum("activo", "inactivo", name="estado_galpon"),
        default="activo"
    )

    sede       = relationship("Sede", back_populates="galpones",
                              lazy="raise")
    containers = relationship("Container", back_populates="galpon",
                              lazy="raise")
    asignaciones = relationship("UsuarioGalpon",
                                back_populates="galpon",
                                lazy="raise")
