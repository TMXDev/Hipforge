from typing import Dict, Set
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        # Dictionary mapping migration_id to a set of active WebSocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, migration_id: str, websocket: WebSocket):
        """Accepts a WebSocket connection and registers it for the given migration_id."""
        await websocket.accept()
        if migration_id not in self.active_connections:
            self.active_connections[migration_id] = set()
        self.active_connections[migration_id].add(websocket)

    def disconnect(self, migration_id: str, websocket: WebSocket):
        """Removes a WebSocket connection from the active list for the given migration_id."""
        if migration_id in self.active_connections:
            self.active_connections[migration_id].discard(websocket)
            if not self.active_connections[migration_id]:
                del self.active_connections[migration_id]

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Sends a JSON message to a specific WebSocket connection."""
        await websocket.send_json(message)

    async def broadcast_to_migration(self, migration_id: str, message: dict):
        """Broadcasts a JSON message to all active WebSocket connections for a given migration_id."""
        if migration_id in self.active_connections:
            # Create a copy of the set to avoid modification during iteration
            for connection in list(self.active_connections[migration_id]):
                try:
                    await connection.send_json(message)
                except Exception:
                    # Connection might have already closed or errored, handle gracefully
                    self.disconnect(migration_id, connection)

manager = ConnectionManager()
