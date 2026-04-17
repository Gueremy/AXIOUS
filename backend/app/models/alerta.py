import uuid
from sqlalchemy import (Column, String, ForeignKey, Enum,
                        DateTime, Text)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class Alerta(Base):
    __tablename__ = "alerta"

    id = Column(String(36), primary_key=True,
                default=lambda: str(uuid.uuid4()))
    id_container       = Column(String(36),
                                ForeignKey("container.id"),
                                nullable=False)
    id_usuario_revision = Column(String(36),
                                  ForeignKey("usuario.id"),
                                  nullable=True)
    tipo = Column(
        Enum(
            "capacidad_critica",
            "vencimiento_30_dias",
            "vencimiento_7_dias",
            "stock_minimo",
            "movimiento_fuera_horario",
            "discrepancia_inventario",
            "sin_movimiento_30_dias",
            "cuarentena_activa",
            name="tipo_alerta"
        ),
        nullable=False
    )
    severidad = Column(
        Enum("critica", "aviso", "informativa",
             name="severidad_alerta"),
        nullable=False
    )
    descripcion      = Column(String(300), nullable=False)
    estado = Column(
        Enum("activa", "revisada", "resuelta",
             name="estado_alerta"),
        default="activa"
    )
    fecha_generacion = Column(DateTime(timezone=True),
                              server_default=func.now())
    fecha_revision   = Column(DateTime(timezone=True),
                              nullable=True)

    container        = relationship("Container",
                                    back_populates="alertas",
                                    lazy="raise")
    usuario_revision = relationship("Usuario", lazy="raise")
