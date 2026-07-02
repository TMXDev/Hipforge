import json
import asyncio
import logging
from fastapi import WebSocket, WebSocketDisconnect
from app.websocket.manager import manager
import app.redis.client
from app.redis.keys import events_channel, compiler_channel, agents_channel

logger = logging.getLogger("websocket_stream")

async def handle_websocket_stream(websocket: WebSocket, migration_id: str):
    """
    Handles the WebSocket lifecycle for a specific migration stream.
    Accepts the connection, subscribes to Redis Pub/Sub channels (events, compiler, agents)
    individually to maintain compatibility with mock clients, sends the initial 
    connected handshake, and relays all events to the client.
    Closes gracefully when a terminal state (COMPLETED or FAILED) is encountered.
    """
    await manager.connect(migration_id, websocket)
    
    pubsub = app.redis.client.redis_client.pubsub()
    # Subscribe individually for compatibility with conftest.py MockPubSub.subscribe signature
    await pubsub.subscribe(events_channel(migration_id))
    await pubsub.subscribe(compiler_channel(migration_id))
    await pubsub.subscribe(agents_channel(migration_id))
    
    try:
        # Send required initial connection handshake
        await manager.send_personal_message(
            {
                "type": "connected",
                "migration_id": migration_id
            },
            websocket
        )
        
        async def client_listener():
            try:
                while True:
                    await websocket.receive_text()
            except WebSocketDisconnect:
                pass
                
        client_task = asyncio.create_task(client_listener())
        
        while not client_task.done():
            # Non-blocking get_message with short timeout
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
            if msg:
                data = msg["data"]
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                
                try:
                    payload = json.loads(data)
                    await websocket.send_json(payload)
                    
                    # Close gracefully on terminal states
                    if payload.get("type") == "event":
                        stage = payload.get("stage")
                        status = payload.get("status")
                        if stage in ("COMPLETED", "FAILED") and status in ("completed", "failed"):
                            # Let the client process the last event before closing the websocket
                            await asyncio.sleep(0.5)
                            break
                except Exception as e:
                    logger.error(f"Error parsing/relaying Pub/Sub message: {e}")
                    
        client_task.cancel()
        
    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected for migration {migration_id}")
    except Exception as e:
        logger.error(f"WebSocket stream error: {e}")
    finally:
        try:
            await pubsub.unsubscribe()
            await pubsub.aclose()
        except Exception:
            pass
        manager.disconnect(migration_id, websocket)
