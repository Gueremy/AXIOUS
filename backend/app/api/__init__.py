from fastapi import APIRouter
from app.api import auth
from app.api import sedes
from app.api import galpones
from app.api import containers
from app.api import productos
from app.api import usuarios

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(sedes.router, prefix="/sedes", tags=["Sedes"])
api_router.include_router(galpones.router, prefix="/galpones", tags=["Galpones"])
api_router.include_router(containers.router, prefix="/containers", tags=["Containers"])
api_router.include_router(productos.router, prefix="/productos", tags=["Productos"])
api_router.include_router(usuarios.router, prefix="/usuarios", tags=["Usuarios"])
