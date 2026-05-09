from fastapi import APIRouter
from app.api import auth
from app.api import sedes
from app.api import galpones
from app.api import containers
from app.api import productos
from app.api import usuarios
from app.api import movimientos
from app.api import alertas
from app.api import dashboard
from app.api import reportes

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(sedes.router, prefix="/sedes", tags=["Sedes"])
api_router.include_router(galpones.router, prefix="/galpones", tags=["Galpones"])
api_router.include_router(containers.router, prefix="/containers", tags=["Containers"])
api_router.include_router(productos.router, prefix="/productos", tags=["Productos"])
api_router.include_router(usuarios.router, prefix="/usuarios", tags=["Usuarios"])
api_router.include_router(movimientos.router, prefix="/movimientos", tags=["Movimientos"])
api_router.include_router(alertas.router, prefix="/alertas", tags=["Alertas"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
api_router.include_router(reportes.router, prefix="/reportes", tags=["Reportes"])

