from fastapi import WebSocket, WebSocketDisconnect
from app.websocket.manager import manager

async def handle_websocket_stream(websocket: WebSocket, migration_id: str):
    """
    Handles the WebSocket lifecycle for a specific migration stream.
    Accepts the connection, sends the initial connection message,
    and listens for disconnects gracefully.
    """
    await manager.connect(migration_id, websocket)
    try:
        # Send the required initial connection message
        await manager.send_personal_message(
            {
                "type": "connected",
                "migration_id": migration_id
            },
            websocket
        )
        
        # Keep the connection open and listen for any incoming data or disconnect events
        while True:
            await websocket.receive_text()
            
    except WebSocketDisconnect:
        manager.disconnect(migration_id, websocket)
    except Exception:
        manager.disconnect(migration_id, websocket)
