"""
app/main.py
Punto de entrada de la aplicación FastAPI.
- Swagger deshabilitado en producción
- Rate limiting con slowapi
- CORS configurado desde .env
- WebSocket para alertas en tiempo real
- APScheduler para jobs nocturnos y periódicos
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError
from sqlalchemy import select
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api import api_router
from app.api.v2 import api_v2_router
from app.core.config import settings
from app.core.limiter import limiter
from app.core.logger import log_sistema_iniciado, log_sistema_detenido
from app.core.security import verify_token
from app.core.dependencies_v2 import get_current_tenant
from app.core.validators.schema_validator import AtributosValidationError
from app.core.events.event_bus import EventBus
from app.database import AsyncSessionLocal, engine
from app.models import *  # noqa: F401, F403 — necesario para que Alembic detecte modelos
from app.models.usuario import Usuario
from app.models.v2.sitio import Sitio
from app.integraciones.webhooks import encolar_evento_webhook
from app.modules.importacion.events import alertar_conciliacion
from app.services.v2.alerta_event_handlers import alertar_movimiento_fuera_horario
from app.websockets import manager
from app.scheduler import scheduler


# ─── Lifespan (startup / shutdown) ───────────────────────────────────────────
@asynccontextmanager
async def lifespan(app):
    log_sistema_iniciado(version="3.0.0", entorno=settings.ENVIRONMENT)
    EventBus.subscribe("movimiento.creado", encolar_evento_webhook)
    EventBus.subscribe("movimiento.rechazado", encolar_evento_webhook)
    EventBus.subscribe("movimiento.etapa_aprobada", encolar_evento_webhook)
    EventBus.subscribe("movimiento.aprobado", encolar_evento_webhook)
    EventBus.subscribe("importacion.finalizada", encolar_evento_webhook)
    EventBus.subscribe("importacion.finalizada", alertar_conciliacion)
    EventBus.subscribe("movimiento.creado", alertar_movimiento_fuera_horario)
    scheduler.start()
    yield
    scheduler.shutdown()
    log_sistema_detenido()


# ─── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Inventario 3D Salmonera — Skretting",
    description="Backend del sistema de gestión de inventario para Skretting. "
                "SERNAPESCA compliance · Multi-sede · 5 roles.",
    version="3.0.0",
    docs_url="/docs"  if settings.ENVIRONMENT == "development" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT == "development" else None,
    lifespan=lifespan,
)

# ─── Middleware ───────────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(AtributosValidationError)
async def atributos_invalidos_handler(request, exc: AtributosValidationError):
    return JSONResponse(status_code=422, content={"detail": exc.message, "errores": exc.errors})

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
)

# ─── Routers ──────────────────────────────────────────────────────────────────
app.include_router(api_router)
app.include_router(api_v2_router)


# ─── WebSocket — Alertas en tiempo real por sede ──────────────────────────────
# BUG-4 FIX: En Render (y cualquier proxy HTTPS), el cliente debe usar wss:// no ws://
# El endpoint está correctamente registrado en app (no en api_router) para que
# el proxy HTTP/1.1 → WS upgrade funcione sin prefijo adicional.
# URL correcta en producción: wss://<host>/ws/alertas/{id_sede}?token=<jwt>
@app.websocket("/ws/alertas/{id_sede}")
async def websocket_alertas(websocket: WebSocket, id_sede: str):
    """
    WebSocket para recibir alertas en tiempo real filtradas por sede.
    Conexión: wss://host/ws/alertas/{id_sede}?token=JWT_TOKEN
    El token JWT debe pasarse como query param (los headers custom no son soportados en WS).
    """
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Token requerido")
        return
    try:
        payload = verify_token(token, expected_type="access")
    except JWTError:
        await websocket.close(code=4001, reason="Token inválido o expirado")
        return

    async with AsyncSessionLocal() as db:
        usuario = (await db.execute(select(Usuario).where(Usuario.id == payload.get("sub")))).scalar_one_or_none()
        if not usuario or not usuario.activo:
            await websocket.close(code=4003, reason="Usuario sin acceso")
            return
        sitio_v2 = (await db.execute(select(Sitio).where(Sitio.id == id_sede))).scalar_one_or_none()
        if sitio_v2:
            try:
                tenant = await get_current_tenant(token=token, db=db)
                tenant.validar_pertenencia_org(sitio_v2.id_organizacion)
                tenant.exigir_acceso_sitio(sitio_v2.id)
            except HTTPException:
                await websocket.close(code=4003, reason="Sitio sin acceso")
                return
        elif usuario.id_sede != id_sede:
            await websocket.close(code=4003, reason="Sede sin acceso")
            return

    await manager.connect(websocket, id_sede)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, id_sede)


# BUG-4 FIX: Endpoint de prueba para verificar que el path WS es alcanzable via HTTP
# Render usa esto para confirmar que el proceso responde en esa ruta
@app.get("/ws/health", tags=["Sistema"])
async def ws_health():
    """Verifica que el path /ws/ está expuesto (útil para diagnóstico en Render)."""
    return {"ws_path": "/ws/alertas/{id_sede}", "protocol": "wss", "status": "reachable"}


# ─── Health check ─────────────────────────────────────────────────────────────
@app.get("/health", tags=["Sistema"])
async def health():
    host = settings.BASE_URL.replace("https://", "").replace("http://", "")
    return {
        "status": "ok",
        "environment": settings.ENVIRONMENT,
        "version": "3.0.0",
        "websocket_connections": manager.total_connections,
        "scheduler_running": scheduler.running,
        # BUG-4 FIX: mostrar URL correcta wss:// para que el frontend sepa cómo conectarse
        "websocket_url": f"wss://{host}/ws/alertas/{{id_sede}}?token={{jwt}}" if settings.ENVIRONMENT == "production" else "ws://localhost:8000/ws/alertas/{id_sede}?token={jwt}",
    }
