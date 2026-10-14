from fastapi import APIRouter

from app.api.v2.sitios import router as sitios_router
from app.api.v2.zonas import router as zonas_router
from app.api.v2.ubicaciones import router as ubicaciones_router
from app.api.v2.items import router as items_router
from app.api.v2.lotes import router as lotes_router
from app.api.v2.esquemas import router as esquemas_router
from app.api.v2.movimientos import router as movimientos_router
from app.api.v2.reglas import router as reglas_router
from app.api.v2.alertas import router as alertas_router
from app.modules.importacion import router as importacion_router
from app.api.v2.dashboard import router as dashboard_router
from app.api.v2.bi import router as bi_router
from app.api.v2.modulos import router as modulos_router
from app.modules.pack_salmonero import router as pack_salmonero_router
from app.modules.picking import router as picking_router
from app.api.v2.layout import router as layout_router
from app.modules.demo.router import router as demo_router
from app.integraciones import router as integraciones_router
from app.api.v2.usuarios import router as usuarios_router
from app.api.v2.roles import router as roles_router
from app.api.v2.configuracion_operativa import router as configuracion_operativa_router
from app.api.v2.exportaciones import router as exportaciones_router
from app.api.v2.sesion import router as sesion_router

api_v2_router = APIRouter(prefix="/api/v2")

api_v2_router.include_router(sitios_router)
api_v2_router.include_router(zonas_router)
api_v2_router.include_router(ubicaciones_router)
api_v2_router.include_router(items_router)
api_v2_router.include_router(lotes_router)
api_v2_router.include_router(esquemas_router)
api_v2_router.include_router(movimientos_router)
api_v2_router.include_router(reglas_router)
api_v2_router.include_router(alertas_router)
api_v2_router.include_router(importacion_router)
api_v2_router.include_router(dashboard_router)
api_v2_router.include_router(bi_router)
api_v2_router.include_router(modulos_router)
api_v2_router.include_router(pack_salmonero_router)
api_v2_router.include_router(picking_router)
api_v2_router.include_router(layout_router)
api_v2_router.include_router(demo_router)
api_v2_router.include_router(integraciones_router)
api_v2_router.include_router(usuarios_router)
api_v2_router.include_router(roles_router)
api_v2_router.include_router(configuracion_operativa_router)
api_v2_router.include_router(exportaciones_router)
api_v2_router.include_router(sesion_router)
