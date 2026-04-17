import uuid
from sqlalchemy import (Column, String, Integer, ForeignKey,
                        Enum, DateTime, Numeric)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class Container(Base):
    __tablename__ = "container"

    id        = Column(String(36), primary_key=True,
                       default=lambda: str(uuid.uuid4()))
    id_galpon = Column(String(36), ForeignKey("galpon.id"),
                       nullable=False)
    codigo    = Column(String(15), nullable=False)   # G1-C04
    posicion_fila = Column(Integer, nullable=False)
    posicion_col  = Column(Integer, nullable=False)
    capacidad_max = Column(Numeric(10, 2), nullable=False)
    unidad_medida = Column(String(20), nullable=False)
    ocupacion_actual = Column(Numeric(10, 2), default=0.0)
    estado = Column(
        Enum("disponible", "medio", "critico",
             "mantenimiento", "cuarentena",
             name="estado_container"),
        default="disponible"
    )
    tipo_producto_permitido = Column(
        Enum("alimento", "quimico", "veterinario",
             "equipo", "repuesto", "general",
             name="tipo_producto_container"),
        default="general"
    )
    temperatura_requerida = Column(Numeric(5, 2), nullable=True)
    motivo_estado         = Column(String(200), nullable=True)
    ultimo_movimiento     = Column(DateTime(timezone=True),
                                   nullable=True)
    qr_code               = Column(String(200), nullable=True)

    galpon      = relationship("Galpon", back_populates="containers",
                               lazy="raise")
    movimientos = relationship(
        "Movimiento",
        foreign_keys="[Movimiento.id_container]",
        back_populates="container",
        lazy="raise",
    )
    alertas     = relationship("Alerta", back_populates="container",
                               lazy="raise")
