import csv
import io
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models.producto import Producto
from app.models.usuario import Usuario
from app.schemas.producto import ProductoCreate, ProductoRead, ProductoUpdate
from app.schemas.common import PaginatedResponse
from app.core.dependencies import get_current_user, require_role
from app.core.audit import log_action
from app.core.logger import log_producto_creado

router = APIRouter()

@router.get("/", response_model=PaginatedResponse[ProductoRead])
async def read_productos(
    categoria: str | None = None,
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: Usuario = Depends(get_current_user)
) -> Any:
    stmt = select(Producto)
    if categoria:
        stmt = stmt.where(Producto.categoria == categoria)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await db.scalar(count_stmt)

    result = await db.execute(stmt.offset(skip).limit(limit))
    productos = result.scalars().all()
    
    return {
        "items": productos,
        "total": total,
        "page": (skip // limit) + 1 if limit > 0 else 1,
        "size": limit,
        "pages": (total + limit - 1) // limit if limit > 0 else 1
    }

@router.post("/", response_model=ProductoRead, status_code=status.HTTP_201_CREATED)
async def create_producto(
    producto_in: ProductoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role(["super_admin", "gerencia"]))
) -> Any:
    prod_existente = (await db.execute(select(Producto).where(Producto.codigo_barras == producto_in.codigo_barras))).scalars().first()
    if prod_existente:
        raise HTTPException(status_code=400, detail="El código de producto ya existe")

    producto = Producto(**producto_in.model_dump())
    db.add(producto)
    await db.commit()
    await db.refresh(producto)

    await log_action(db, current_user.id, "CREAR_PRODUCTO", "Producto", str(producto.id), producto_in.model_dump())
    await db.commit()

    log_producto_creado(
        nombre_usuario=current_user.nombre,
        nombre_producto=producto.nombre,
        codigo=producto.codigo_barras,
    )

    return producto

@router.patch("/{id}", response_model=ProductoRead)
async def update_producto(
    id: str,
    producto_in: ProductoUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role(["super_admin"]))
) -> Any:
    stmt = select(Producto).where(Producto.id == id)
    result = await db.execute(stmt)
    producto = result.scalars().first()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    update_data = producto_in.model_dump(exclude_unset=True)
    if not update_data:
        return producto

    for field, value in update_data.items():
        setattr(producto, field, value)
    
    await log_action(db, current_user.id, "ACTUALIZAR_PRODUCTO", "Producto", str(producto.id), update_data)
    await db.commit()
    await db.refresh(producto)
    return producto

@router.post("/importar", status_code=status.HTTP_201_CREATED)
async def importar_productos_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(require_role(["super_admin"]))
) -> Any:
    if not file.filename.endswith(".csv"):
        raise HTTPException(400, "El archivo debe ser un CSV válido con extensión .csv")
        
    content = await file.read()
    decoded = content.decode("utf-8")
    reader = csv.DictReader(io.StringIO(decoded))
    
    required_cols = ["nombre", "codigo_barras", "categoria", "unidad_medida", "stock_minimo"]
    for col in required_cols:
        if col not in reader.fieldnames:
            raise HTTPException(400, f"Falta la columna requerida: {col}")
            
    insertados = 0
    errores = []
    
    for idx, row in enumerate(reader):
        try:
            prod_existente = (await db.execute(select(Producto).where(Producto.codigo_barras == row["codigo_barras"]))).scalars().first()
            if prod_existente:
                errores.append(f"Fila {idx+2}: Código {row['codigo_barras']} ya existe.")
                continue
                
            nuevo_prod = Producto(
                nombre=row["nombre"],
                codigo_barras=row["codigo_barras"],
                categoria=row["categoria"],
                unidad_medida=row["unidad_medida"],
                stock_minimo=float(row["stock_minimo"]),
                descripcion=row.get("descripcion", "")
            )
            db.add(nuevo_prod)
            insertados += 1
        except Exception as e:
            errores.append(f"Fila {idx+2}: Error al procesar ({str(e)})")
            
    if insertados > 0:
        await log_action(db, current_user.id, "IMPORTAR_PRODUCTOS", "Producto", "MASIVO", {"cantidad": insertados})
        await db.commit()
        
    return {
        "mensaje": "Procesamiento completado",
        "insertados": insertados,
        "errores": errores
    }
