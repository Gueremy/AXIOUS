import json
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.log_auditoria import LogAuditoria

async def log_action(
    db: AsyncSession,
    id_usuario: str,
    accion: str,
    entidad: str,
    id_entidad: str,
    detalles: dict = None
):
    """
    Registra una acción crítica en la tabla de auditoría para trazabilidad.
    Nota: no hace db.commit(), deja que el router lo haga en su transacción.
    """
    if detalles is None:
        detalles = {}
        
    log = LogAuditoria(
        id_usuario=id_usuario,
        accion=accion,
        entidad_afectada=entidad,
        id_entidad=id_entidad,
        detalles=detalles
    )
    db.add(log)
