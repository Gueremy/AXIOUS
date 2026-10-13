from fastapi import APIRouter, Depends
from app.core.dependencies import require_legacy_user
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
api_router.include_router(sedes.router, prefix="/sedes", tags=["Sedes"], dependencies=[Depends(require_legacy_user)])
api_router.include_router(galpones.router, prefix="/galpones", tags=["Galpones"], dependencies=[Depends(require_legacy_user)])
api_router.include_router(containers.router, prefix="/containers", tags=["Containers"], dependencies=[Depends(require_legacy_user)])
api_router.include_router(productos.router, prefix="/productos", tags=["Productos"], dependencies=[Depends(require_legacy_user)])
api_router.include_router(usuarios.router, prefix="/usuarios", tags=["Usuarios"], dependencies=[Depends(require_legacy_user)])
api_router.include_router(movimientos.router, prefix="/movimientos", tags=["Movimientos"], dependencies=[Depends(require_legacy_user)])
api_router.include_router(alertas.router, prefix="/alertas", tags=["Alertas"], dependencies=[Depends(require_legacy_user)])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"], dependencies=[Depends(require_legacy_user)])
api_router.include_router(reportes.router, prefix="/reportes", tags=["Reportes"], dependencies=[Depends(require_legacy_user)])

