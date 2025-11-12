"""WebSocket support for real-time comparison progress updates."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from backend.logging_config import get_logger

logger = get_logger(__name__)


class ProgressBroadcaster:
    """Manages WebSocket connections for progress updates."""

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        """Register a new WebSocket connection for a session."""
        await websocket.accept()
        async with self._lock:
            if session_id not in self._connections:
                self._connections[session_id] = []
            self._connections[session_id].append(websocket)
        logger.info("websocket_connected", session_id=session_id)

    async def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        async with self._lock:
            if session_id in self._connections:
                if websocket in self._connections[session_id]:
                    self._connections[session_id].remove(websocket)
                if not self._connections[session_id]:
                    del self._connections[session_id]
        logger.info("websocket_disconnected", session_id=session_id)

    async def broadcast(self, session_id: str, message: dict[str, Any]) -> None:
        """Send a message to all connected clients for a session."""
        async with self._lock:
            connections = self._connections.get(session_id, []).copy()

        if not connections:
            return

        message_json = json.dumps(message)
        disconnected = []

        for websocket in connections:
            try:
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_text(message_json)
                else:
                    disconnected.append(websocket)
            except Exception as exc:
                logger.warning("websocket_send_failed", session_id=session_id, error=str(exc))
                disconnected.append(websocket)

        # Clean up disconnected clients
        if disconnected:
            async with self._lock:
                if session_id in self._connections:
                    for ws in disconnected:
                        if ws in self._connections[session_id]:
                            self._connections[session_id].remove(ws)
                    if not self._connections[session_id]:
                        del self._connections[session_id]

    def create_callback(self, session_id: str) -> Callable[[dict[str, Any]], None]:
        """Create a synchronous callback that queues messages for async broadcast."""
        
        def callback(message: dict[str, Any]) -> None:
            # Schedule the broadcast to run in the event loop
            try:
                loop = asyncio.get_event_loop()
                loop.create_task(self.broadcast(session_id, message))
            except RuntimeError:
                # No event loop available, log and skip
                logger.warning("no_event_loop_for_broadcast", session_id=session_id)
        
        return callback


# Global broadcaster instance
_broadcaster = ProgressBroadcaster()


def get_broadcaster() -> ProgressBroadcaster:
    """Get the global progress broadcaster instance."""
    return _broadcaster


async def progress_websocket_endpoint(websocket: WebSocket, session_id: str) -> None:
    """WebSocket endpoint handler for progress updates."""
    broadcaster = get_broadcaster()
    await broadcaster.connect(session_id, websocket)
    
    try:
        # Keep the connection open and listen for client disconnect
        while True:
            try:
                # Wait for any message from client (typically just ping/pong)
                await websocket.receive_text()
            except WebSocketDisconnect:
                break
    finally:
        await broadcaster.disconnect(session_id, websocket)


__all__ = ["progress_websocket_endpoint", "get_broadcaster"]

