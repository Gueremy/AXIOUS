import uuid
from sqlalchemy import (Column, String, Boolean, ForeignKey,
                        Enum, DateTime, Integer)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class Usuario(Base):
    __tablename__ = "usuario"

    id              = Column(String(36), primary_key=True,
                             default=lambda: str(uuid.uuid4()))
    nombre          = Column(String(100), nullable=False)
    email           = Column(String(150), nullable=False,
                             unique=True)
    password_hash   = Column(String(255), nullable=False)
    rut             = Column(String(12),  nullable=True)   # INTERNO SOLO
    codigo_empleado = Column(String(20),  nullable=False,
                             unique=True)
    rol = Column(
        Enum("super_admin", "admin_sede", "jefe_bodega",
             "operario", "gerencia", name="rol_usuario"),
        nullable=False
    )
    id_sede = Column(String(36), ForeignKey("sede.id"),
                     nullable=True)
    turno   = Column(Enum("A", "B", name="turno_usuario"),
                     nullable=True)
    activo  = Column(Boolean, default=True)
    fecha_creacion = Column(DateTime(timezone=True),
                            server_default=func.now())
    ultimo_acceso  = Column(DateTime(timezone=True),
                            nullable=True)
    # Seguridad y Recuperación
    intentos_fallidos = Column(Integer, default=0)
    bloqueo_hasta     = Column(DateTime(timezone=True), nullable=True)
    reset_token       = Column(String(255), nullable=True)
    reset_token_expire= Column(DateTime(timezone=True), nullable=True)

    sede         = relationship("Sede", back_populates="usuarios",
                                lazy="raise")
    movimientos  = relationship("Movimiento",
                                foreign_keys="Movimiento.id_usuario",
                                back_populates="usuario",
                                lazy="raise")
    aprobaciones = relationship("Movimiento",
                                foreign_keys="Movimiento.id_usuario_aprobador",
                                back_populates="usuario_aprobador",
                                lazy="raise")
    asignaciones = relationship("UsuarioGalpon",
                                back_populates="usuario",
                                lazy="raise")


class UsuarioGalpon(Base):
    """Tabla pivot N:M — operario puede tener varios galpones."""
    __tablename__ = "usuario_galpon"

    id_usuario        = Column(String(36), ForeignKey("usuario.id"),
                               primary_key=True)
    id_galpon         = Column(String(36), ForeignKey("galpon.id"),
                               primary_key=True)
    fecha_asignacion  = Column(DateTime(timezone=True),
                               server_default=func.now())

    usuario = relationship("Usuario", back_populates="asignaciones",
                           lazy="raise")
    galpon  = relationship("Galpon",  back_populates="asignaciones",
                           lazy="raise")
