import json
from typing import Tuple, Dict, Any, Optional
from app.redis.client import redis_client
from app.redis.keys import pending_queue_key, active_queue_key

async def enqueue_job(migration_id: str, payload: Dict[str, Any]) -> None:
    """
    Pushes a new migration job to the pending queue.
    The payload dictionary is merged with migration_id and serialized to JSON.
    """
    key = pending_queue_key()
    full_payload = {
        "migration_id": migration_id,
        **payload
    }
    await redis_client.lpush(key, json.dumps(full_payload))

async def dequeue_job(timeout: int = 0) -> Optional[Tuple[str, Dict[str, Any]]]:
    """
    Blocks and waits for a job to be pushed onto the pending queue.
    Returns a tuple of (migration_id, payload) or None if the timeout is reached.
    """
    key = pending_queue_key()
    result = await redis_client.brpop(key, timeout=timeout)
    if not result:
        return None
    
    # brpop returns a tuple of (list_key, value)
    _, value = result
    payload = json.loads(value)
    migration_id = payload.get("migration_id")
    return migration_id, payload

async def mark_active(migration_id: str) -> None:
    """
    Records a migration job ID in the active queue to indicate processing has started.
    """
    key = active_queue_key()
    await redis_client.lpush(key, migration_id)

async def mark_done(migration_id: str) -> None:
    """
    Removes a migration job ID from the active queue to indicate completion or termination.
    """
    key = active_queue_key()
    # lrem removes all occurrences (count=0) matching migration_id
    await redis_client.lrem(key, 0, migration_id)
