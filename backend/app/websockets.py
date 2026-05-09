"""
app/websockets.py
ConnectionManager para alertas en tiempo real por sede.
Patrón documentado en GUIDELINES.md (líneas 452-473).
"""
import logging
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Gestiona conexiones WebSocket agrupadas por id_sede."""

    def __init__(self):
        self.connections: dict[str, list[WebSocket]] = {}

    async def connect(self, ws: WebSocket, id_sede: str):
        await ws.accept()
        self.connections.setdefault(id_sede, []).append(ws)
        logger.info(f"WS conectado: sede={id_sede} (total={len(self.connections[id_sede])})")

    def disconnect(self, ws: WebSocket, id_sede: str):
        if ws in self.connections.get(id_sede, []):
            self.connections[id_sede].remove(ws)
            logger.info(f"WS desconectado: sede={id_sede}")

    async def broadcast_sede(self, id_sede: str, mensaje: dict):
        """Envía mensaje JSON a todos los clientes conectados de una sede."""
        muertos = []
        for ws in self.connections.get(id_sede, []):
            try:
                await ws.send_json(mensaje)
            except Exception:
                muertos.append(ws)
        for ws in muertos:
            self.disconnect(ws, id_sede)

    @property
    def total_connections(self) -> int:
        return sum(len(v) for v in self.connections.values())


# Instancia singleton — importar desde aquí en todo el proyecto
manager = ConnectionManager()
