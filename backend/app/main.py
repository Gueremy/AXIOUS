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
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api import api_router
from app.core.config import settings
from app.database import engine
from app.models import *  # noqa: F401, F403 — necesario para que Alembic detecte modelos
from app.websockets import manager
from app.scheduler import scheduler

# ─── Rate limiter ─────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)


# ─── Lifespan (startup / shutdown) ───────────────────────────────────────────
@asynccontextmanager
async def lifespan(app):
    # Startup
    scheduler.start()
    yield
    # Shutdown
    scheduler.shutdown()


# ─── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Inventario 3D Salmonera — Skretting",
    description="Backend del sistema de gestión de inventario para Skretting. "
                "SERNAPESCA compliance · Multi-sede · 5 roles.",
    version="3.0.0",
    # Swagger y ReDoc solo en desarrollo
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
    allow_methods=["*"],
    allow_headers=["*"],
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
    # TODO: Validar JWT desde query param en producción
    # token = websocket.query_params.get("token")
    # if not token or not validate_jwt(token): await websocket.close(4001); return
    await manager.connect(websocket, id_sede)
    try:
        while True:
            # Mantener conexión viva — el cliente puede enviar pings
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
