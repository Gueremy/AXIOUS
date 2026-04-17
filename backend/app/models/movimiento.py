import uuid
from sqlalchemy import (Column, String, ForeignKey, Enum,
                        DateTime, Numeric, Boolean, Text)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class Movimiento(Base):
    __tablename__ = "movimiento"

    id = Column(String(36), primary_key=True,
                default=lambda: str(uuid.uuid4()))

    # FKs principales
    id_container          = Column(String(36),
                                   ForeignKey("container.id"),
                                   nullable=False)
    id_container_destino  = Column(String(36),
                                   ForeignKey("container.id"),
                                   nullable=True)
    id_usuario            = Column(String(36),
                                   ForeignKey("usuario.id"),
                                   nullable=False)
    id_usuario_aprobador  = Column(String(36),
                                   ForeignKey("usuario.id"),
                                   nullable=True)
    id_producto           = Column(String(36),
                                   ForeignKey("producto.id"),
                                   nullable=False)
    id_movimiento_original = Column(String(36),
                                    ForeignKey("movimiento.id"),
                                    nullable=True)   # solo en correcciones

    # Tipo y estado
    tipo = Column(
        Enum("entrada_proveedor", "salida_produccion",
             "traslado_interno", "correccion",
             name="tipo_movimiento"),
        nullable=False
    )
    estado = Column(
        Enum("pendiente", "aprobado", "rechazado",
             name="estado_movimiento"),
        default="pendiente"
    )
    cantidad = Column(Numeric(10, 2), nullable=False)

    # Campos SERNAPESCA obligatorios
    numero_lote        = Column(String(50),  nullable=False)
    fecha_fabricacion  = Column(DateTime(timezone=True),
                                nullable=True)
    fecha_vencimiento  = Column(DateTime(timezone=True),
                                nullable=False)
    nombre_proveedor   = Column(String(150), nullable=True)
    rut_proveedor      = Column(String(12),  nullable=True)   # INTERNO SOLO
    num_guia_despacho  = Column(String(50),  nullable=True)
    registro_sanitario = Column(String(50),  nullable=True)
    temperatura_almacen = Column(Numeric(5, 2), nullable=True)

    # Campos SAG (solo medicamentos veterinarios)
    num_receta_retenida  = Column(String(50), nullable=True)
    num_autorizacion_sag = Column(String(50), nullable=True)

    # Control
    fecha_hora       = Column(DateTime(timezone=True),
                              server_default=func.now(),
                              nullable=False)
    fecha_aprobacion = Column(DateTime(timezone=True),
                              nullable=True)
    motivo_rechazo   = Column(String(300), nullable=True)
    observaciones    = Column(String(300), nullable=True)
    origen = Column(
        Enum("online", "offline_sync", name="origen_movimiento"),
        default="online"
    )
    flag_fefo = Column(Boolean, default=False)

    # Relaciones
    container          = relationship("Container",
                                      foreign_keys=[id_container],
                                      back_populates="movimientos",
                                      lazy="raise")
    container_destino  = relationship("Container",
                                      foreign_keys=[id_container_destino],
                                      lazy="raise")
    usuario            = relationship("Usuario",
                                      foreign_keys=[id_usuario],
                                      back_populates="movimientos",
                                      lazy="raise")
    usuario_aprobador  = relationship("Usuario",
                                      foreign_keys=[id_usuario_aprobador],
                                      back_populates="aprobaciones",
                                      lazy="raise")
    producto           = relationship("Producto", lazy="raise")
    correccion_original = relationship("Movimiento",
                                       remote_side="Movimiento.id",
                                       lazy="raise")
