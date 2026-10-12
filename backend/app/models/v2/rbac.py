"""
app/models/v2/rbac.py
Modelos de Roles y Permisos configurables por organización (RBAC v2).
Soporta plantilla inicial de los 5 roles tradicionales y asignación granular de sitios.
"""
import uuid
from sqlalchemy import (
    Column, String, Boolean, DateTime,
    ForeignKey, Table, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Rol(Base):
    __tablename__ = "v2_rol"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    id_organizacion = Column(String(36), ForeignKey("v2_organizacion.id", ondelete="CASCADE"), nullable=False, index=True)
    codigo = Column(String(50), nullable=False)  # e.g., 'super_admin', 'admin_sede', 'jefe_bodega', 'operario', 'gerencia'
    nombre = Column(String(100), nullable=False)
    descripcion = Column(String(250), nullable=True)
    es_sistema = Column(Boolean, default=False, nullable=False)
    activo = Column(Boolean, default=True, nullable=False)
    fecha_creacion = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("id_organizacion", "codigo", name="uq_rol_org_codigo"),
    )

    # Relaciones
    permisos = relationship("Permiso", secondary="v2_rol_permiso", back_populates="roles")


class Permiso(Base):
    __tablename__ = "v2_permiso"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    codigo = Column(String(100), unique=True, nullable=False, index=True)  # e.g., 'sitio:read', 'item:write', etc.
    modulo = Column(String(50), nullable=False)
    descripcion = Column(String(200), nullable=True)

    # Relaciones
    roles = relationship("Rol", secondary="v2_rol_permiso", back_populates="permisos")


class RolPermiso(Base):
    __tablename__ = "v2_rol_permiso"

    id_rol = Column(String(36), ForeignKey("v2_rol.id", ondelete="CASCADE"), primary_key=True)
    id_permiso = Column(String(36), ForeignKey("v2_permiso.id", ondelete="CASCADE"), primary_key=True)


class UsuarioSitio(Base):
    """Restricción de acceso por sitio: un usuario puede tener asignados sitios específicos."""
    __tablename__ = "v2_usuario_sitio"

    id_usuario = Column(String(36), ForeignKey("usuario.id", ondelete="CASCADE"), primary_key=True)
    id_sitio = Column(String(36), ForeignKey("v2_sitio.id", ondelete="CASCADE"), primary_key=True)
    fecha_asignacion = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
