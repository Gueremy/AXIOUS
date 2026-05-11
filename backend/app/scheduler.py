"""
app/scheduler.py
APScheduler 3.x — Jobs programados para alertas automáticas.

Job 1: CronTrigger(hour=2) — vencimientos y containers sin movimiento (nocturno)
Job 2: IntervalTrigger(minutes=30) — stock mínimo y discrepancias

⚠️ SIEMPRE ejecutar con --workers 1 (GUIDELINES.md): APScheduler se duplica con más.
"""
import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import delete

from app.database import AsyncSessionLocal
from app.models.refresh_token import RefreshToken
from app.services.alertas import evaluar_alertas_batch
from app.core.logger import log_job_scheduler, log_job_scheduler_error

logger = logging.getLogger(__name__)


async def job_nightly_alerts():
    """
    Job 1: Cron a las 02:00 AM (America/Santiago).
    Evalúa vencimientos (7 y 30 días) y containers sin movimiento.
    """
    logger.info("⏰ Job nocturno iniciando: vencimientos + sin_movimiento")
    try:
        async with AsyncSessionLocal() as db:
            total = await evaluar_alertas_batch(
                db,
                tipos=["vencimiento_7_dias", "vencimiento_30_dias", "sin_movimiento_30_dias"],
            )
            log_job_scheduler(
                descripcion="Revisión nocturna de vencimientos y contenedores sin movimiento",
                resultado=f"Se detectaron {total} alertas nuevas",
            )
    except Exception as e:
        log_job_scheduler_error(
            descripcion="Revisión nocturna de vencimientos y contenedores sin movimiento",
            error=str(e),
        )
        logger.error(f"⏰ Job nocturno ERROR: {e}", exc_info=True)


async def job_periodic_checks():
    """
    Job 2: Cada 30 minutos.
    Evalúa stock mínimo y discrepancias de inventario.
    """
    logger.info("🔄 Job periódico iniciando: stock_minimo + discrepancias")
    try:
        async with AsyncSessionLocal() as db:
            total = await evaluar_alertas_batch(
                db,
                tipos=["stock_minimo", "discrepancia_inventario"],
            )
            log_job_scheduler(
                descripcion="Revisión periódica de stock mínimo y discrepancias de inventario",
                resultado=f"Se detectaron {total} alertas nuevas",
            )
    except Exception as e:
        log_job_scheduler_error(
            descripcion="Revisión periódica de stock mínimo y discrepancias de inventario",
            error=str(e),
        )
        logger.error(f"🔄 Job periódico ERROR: {e}", exc_info=True)


async def job_cleanup_tokens():
    """Elimina refresh tokens expirados de la BD."""
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                delete(RefreshToken).where(
                    RefreshToken.fecha_expiracion < datetime.now(timezone.utc)
                )
            )
            await db.commit()
            logger.info(f"Cleanup tokens: {result.rowcount} tokens expirados eliminados")
    except Exception as e:
        logger.error(f"Cleanup tokens ERROR: {e}", exc_info=True)


# ── Scheduler singleton ──────────────────────────────────────────────────────
scheduler = AsyncIOScheduler(timezone="America/Santiago")

scheduler.add_job(
    job_nightly_alerts,
    CronTrigger(hour=2),
    id="nightly_alerts",
    name="Vencimientos y containers sin movimiento",
    replace_existing=True,
)

scheduler.add_job(
    job_periodic_checks,
    IntervalTrigger(minutes=30),
    id="periodic_checks",
    name="Stock mínimo y discrepancias",
    replace_existing=True,
)

scheduler.add_job(
    job_cleanup_tokens,
    CronTrigger(hour=3),
    id="cleanup_tokens",
    name="Limpieza refresh tokens expirados",
    replace_existing=True,
)

logger.info(f"APScheduler configurado con {len(scheduler.get_jobs())} jobs")
