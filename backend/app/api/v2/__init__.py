from fastapi import APIRouter

from app.api.v2.sitios import router as sitios_router
from app.api.v2.zonas import router as zonas_router
from app.api.v2.ubicaciones import router as ubicaciones_router
from app.api.v2.items import router as items_router
from app.api.v2.lotes import router as lotes_router
from app.api.v2.esquemas import router as esquemas_router
from app.api.v2.movimientos import router as movimientos_router
from app.api.v2.reglas import router as reglas_router

api_v2_router = APIRouter(prefix="/api/v2")

api_v2_router.include_router(sitios_router)
api_v2_router.include_router(zonas_router)
api_v2_router.include_router(ubicaciones_router)
api_v2_router.include_router(items_router)
api_v2_router.include_router(lotes_router)
api_v2_router.include_router(esquemas_router)
api_v2_router.include_router(movimientos_router)
api_v2_router.include_router(reglas_router)
