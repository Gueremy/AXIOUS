import uuid
from sqlalchemy import Column, String, Boolean, Numeric, Enum
from app.database import Base

class Producto(Base):
    __tablename__ = "producto"

    id       = Column(String(36), primary_key=True,
                      default=lambda: str(uuid.uuid4()))
    nombre   = Column(String(150), nullable=False)
    categoria = Column(
        Enum("alimento", "quimico", "veterinario",
             "equipo", "repuesto", "general",
             name="categoria_producto"),
        nullable=False
    )
    codigo_barras       = Column(String(50),  nullable=True)
    unidad_medida       = Column(String(20),  nullable=False)
    temperatura_requerida = Column(Numeric(5, 2), nullable=True)
    stock_minimo        = Column(Numeric(10, 2), nullable=True)
    descripcion         = Column(String(300), nullable=True)
    activo              = Column(Boolean, default=True)
