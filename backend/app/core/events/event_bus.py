"""
app/core/events/event_bus.py
Bus de eventos interno desacoplado (Fase 2B).
Permite comunicación entre el núcleo de movimientos, reglas, packs de industria
y auditoría sin dependencias circulares directas.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Any, Callable, Coroutine, Dict, List, Union

logger = logging.getLogger("app.events")


@dataclass
class DomainEvent:
    name: str
    id_organizacion: str
    payload: Dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


HandlerType = Callable[[DomainEvent], Union[None, Coroutine[Any, Any, None]]]


class EventBus:
    _subscribers: Dict[str, List[HandlerType]] = {}

    @classmethod
    def subscribe(cls, event_name: str, handler: HandlerType) -> None:
        """Registra un suscriptor para un tipo de evento específico."""
        subscribers = cls._subscribers.setdefault(event_name, [])
        if handler not in subscribers:
            subscribers.append(handler)

    @classmethod
    def clear(cls) -> None:
        """Limpia los suscriptores (útil para tests)."""
        cls._subscribers.clear()

    @classmethod
    async def publish(cls, event: DomainEvent) -> None:
        """
        Publica un evento a todos los suscriptores registrados.
        Garantiza que el fallo de un suscriptor no corrompa la transacción principal.
        """
        handlers = cls._subscribers.get(event.name, [])
        for handler in handlers:
            try:
                res = handler(event)
                if hasattr(res, "__await__"):
                    await res
            except Exception as exc:
                logger.error(f"Error en manejador de evento '{event.name}' para org '{event.id_organizacion}': {exc}", exc_info=True)
