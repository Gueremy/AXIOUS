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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api import api_router
from app.core.config import settings
from app.core.limiter import limiter
from app.core.logger import log_sistema_iniciado, log_sistema_detenido
from app.core.security import verify_token
from app.database import engine
from app.models import *  # noqa: F401, F403 — necesario para que Alembic detecte modelos
from app.websockets import manager
from app.scheduler import scheduler


# ─── Lifespan (startup / shutdown) ───────────────────────────────────────────
@asynccontextmanager
async def lifespan(app):
    log_sistema_iniciado(version="3.0.0", entorno=settings.ENVIRONMENT)
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
)

# ─── Routers ──────────────────────────────────────────────────────────────────
app.include_router(api_router)


# ─── WebSocket — Alertas en tiempo real por sede ──────────────────────────────
@app.websocket("/ws/alertas/{id_sede}")
async def websocket_alertas(websocket: WebSocket, id_sede: str):
    """
    WebSocket para recibir alertas en tiempo real filtradas por sede.
    Conexión: ws://host/ws/alertas/{id_sede}?token=JWT_TOKEN
    """
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Token requerido")
        return
    try:
        verify_token(token, expected_type="access")
    except JWTError:
        await websocket.close(code=4001, reason="Token inválido o expirado")
        return

    await manager.connect(websocket, id_sede)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, id_sede)


# ─── Health check ─────────────────────────────────────────────────────────────
@app.get("/health", tags=["Sistema"])
async def health():
    return {
        "status": "ok",
        "environment": settings.ENVIRONMENT,
        "version": "3.0.0",
        "websocket_connections": manager.total_connections,
        "scheduler_running": scheduler.running,
    }
