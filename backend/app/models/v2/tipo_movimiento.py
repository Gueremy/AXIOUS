"""
app/models/v2/tipo_movimiento.py
Tipos de movimiento configurables por organización.
Distingue nombre visible de su efecto contable sobre existencias (entrada, salida, traslado, sin_efecto).
"""
import uuid
from sqlalchemy import Column, String, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database import Base


class TipoMovimiento(Base):
    __tablename__ = "v2_tipo_movimiento"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    id_organizacion = Column(String(36), ForeignKey("v2_organizacion.id", ondelete="CASCADE"), nullable=False, index=True)
    codigo = Column(String(50), nullable=False)  # e.g. 'ENTRADA_COMPRA', 'DESPACHO_VENTA', 'TRASLADO_INTERNO'
    nombre = Column(String(100), nullable=False)
    efecto_stock = Column(String(20), nullable=False)  # 'entrada', 'salida', 'traslado', 'sin_efecto'
    requiere_origen = Column(Boolean, default=False, nullable=False)
    requiere_destino = Column(Boolean, default=False, nullable=False)
    requiere_aprobacion = Column(Boolean, default=False, nullable=False)
    activo = Column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("id_organizacion", "codigo", name="uq_tipo_mov_org_codigo"),
    )
