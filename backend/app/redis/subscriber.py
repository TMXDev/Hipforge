import redis.asyncio as aioredis
from app.redis.client import redis_client
from app.redis.keys import events_channel

async def subscribe_to_migration(migration_id: str) -> aioredis.client.PubSub:
    """
    Subscribes to the events channel for the given migration_id
    and returns the active PubSub subscriber object.
    """
    channel = events_channel(migration_id)
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(channel)
    return pubsub
