import json
from datetime import datetime, timezone
from app.redis.client import redis_client
from app.redis.keys import events_channel

async def publish_event(migration_id: str, stage: str, status: str, message: str) -> int:
    """
    Publishes a migration progress event to the Pub/Sub events channel.
    The channel name is resolved via keys.py.
    The payload contains: type, migration_id, timestamp, stage, status, and message.
    """
    channel = events_channel(migration_id)
    timestamp = datetime.now(timezone.utc).isoformat()
    
    payload = {
        "type": "event",
        "migration_id": migration_id,
        "timestamp": timestamp,
        "stage": stage,
        "status": status,
        "message": message,
        "state": stage,       # Compatibility field
        "details": message    # Compatibility field
    }
    
    # Returns the number of subscribers that received the message
    return await redis_client.publish(channel, json.dumps(payload))
