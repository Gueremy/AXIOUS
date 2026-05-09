"""
app/main.py
Punto de entrada de la aplicación FastAPI.
- Swagger deshabilitado en producción
- Rate limiting con slowapi
- CORS configurado para desarrollo
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api import api_router
from app.core.config import settings
from app.database import engine
from app.models import *  # noqa: F401, F403 — necesario para que Alembic detecte modelos

# ─── Rate limiter ─────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)

# ─── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Inventario 3D Salmonera — Skretting",
    description="Backend del sistema de gestión de inventario para Skretting. "
                "SERNAPESCA compliance · Multi-sede · 5 roles.",
    version="2.0.0",
    # Swagger y ReDoc solo en desarrollo
    docs_url="/docs"  if settings.ENVIRONMENT == "development" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT == "development" else None,
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


# ─── Health check ─────────────────────────────────────────────────────────────
@app.get("/health", tags=["Sistema"])
async def health():
    return {
        "status": "ok",
        "environment": settings.ENVIRONMENT,
        "version": "2.0.0",
    }
