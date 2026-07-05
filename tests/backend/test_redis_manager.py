import pytest
import asyncio
import json
from app.redis import keys
import app.redis.client

async def enqueue_job(migration_id: str, payload: dict) -> None:
    key = keys.pending_queue_key()
    await app.redis.client.redis_client.lpush(key, json.dumps({"migration_id": migration_id, **payload}))

async def dequeue_job(timeout: int = 0):
    key = keys.pending_queue_key()
    result = await app.redis.client.redis_client.brpop(key, timeout=timeout)
    if not result:
        return None
    _, value = result
    payload = json.loads(value)
    return payload.get("migration_id"), payload

async def mark_active(migration_id: str) -> None:
    await app.redis.client.redis_client.lpush(keys.active_queue_key(), migration_id)

async def mark_done(migration_id: str) -> None:
    await app.redis.client.redis_client.lrem(keys.active_queue_key(), 0, migration_id)

async def subscribe_to_migration(migration_id: str):
    pubsub = app.redis.client.redis_client.pubsub()
    await pubsub.subscribe(keys.events_channel(migration_id))
    return pubsub

async def publish_event(migration_id: str, stage: str, status: str, message: str) -> int:
    from datetime import datetime, timezone
    channel = keys.events_channel(migration_id)
    payload = {
        "type": "event",
        "migration_id": migration_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "status": status,
        "message": message,
        "state": stage,
        "details": message
    }
    return await app.redis.client.redis_client.publish(channel, json.dumps(payload))

def test_key_builders():
    """
    Test Case 1: Verifies that every key builder function in keys.py returns the correct key patterns.
    """
    migration_id = "test-migration-id-123"
    
    assert keys.pending_queue_key(migration_id) == "hipforge:queue:pending"
    assert keys.active_queue_key(migration_id) == "hipforge:queue:active"
    assert keys.status_key(migration_id) == f"migration:{migration_id}:status"
    assert keys.attempt_key(migration_id) == f"migration:{migration_id}:attempt"
    assert keys.retry_budget_key(migration_id) == f"migration:{migration_id}:retry_budget"
    assert keys.compiler_log_key(migration_id) == f"migration:{migration_id}:compiler_log"
    assert keys.analysis_key(migration_id) == f"migration:{migration_id}:analysis"
    assert keys.patch_key(migration_id) == f"migration:{migration_id}:patch"
    assert keys.research_key(migration_id) == f"migration:{migration_id}:research"
    assert keys.journal_key(migration_id) == f"migration:{migration_id}:journal"
    assert keys.metadata_key(migration_id) == f"migration:{migration_id}:metadata"
    assert keys.events_channel(migration_id) == f"migration:{migration_id}:events"
    assert keys.compiler_channel(migration_id) == f"migration:{migration_id}:compiler"
    assert keys.agents_channel(migration_id) == f"migration:{migration_id}:agents"

def test_enqueue_dequeue_roundtrip(redis_test_client):
    """
    Test Case 2: Verifies that enqueuing a job correctly serializes the payload and dequeuing retrieves it.
    """
    migration_id = "roundtrip-id-456"
    payload = {
        "workspace_path": "/app/workspace/roundtrip-id-456",
        "retry_budget": 5,
        "migration_mode": "full"
    }
    
    async def run_test():
        await enqueue_job(migration_id, payload)
        dequeued = await dequeue_job(timeout=1)
        
        assert dequeued is not None
        deq_migration_id, deq_payload = dequeued
        
        assert deq_migration_id == migration_id
        assert deq_payload["workspace_path"] == payload["workspace_path"]
        assert deq_payload["retry_budget"] == payload["retry_budget"]
        assert deq_payload["migration_mode"] == payload["migration_mode"]

    asyncio.run(run_test())

def test_active_job_lifecycle(redis_test_client):
    """
    Test Case 3: Verifies that marking jobs as active adds them to the active list and marking them done removes them.
    """
    migration_id = "lifecycle-id-789"
    active_key = keys.active_queue_key()
    
    async def run_test():
        await mark_active(migration_id)
        active_jobs = await redis_test_client.lrange(active_key, 0, -1)
        assert migration_id in active_jobs
        
        await mark_done(migration_id)
        active_jobs_after = await redis_test_client.lrange(active_key, 0, -1)
        assert migration_id not in active_jobs_after

    asyncio.run(run_test())

def test_pubsub_event_delivery(redis_test_client):
    """
    Test Case 4: Verifies that publishing a progress event is successfully received by a subscriber.
    """
    migration_id = "pubsub-id-abc"
    stage = "COMPILING"
    status = "in_progress"
    message = "Building project..."
    
    async def run_test():
        pubsub = await subscribe_to_migration(migration_id)
        await asyncio.sleep(0.05)
        
        subscribers_count = await publish_event(migration_id, stage, status, message)
        assert subscribers_count > 0
        
        received_message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
        
        assert received_message is not None
        assert received_message["type"] == "message"
        
        payload = json.loads(received_message["data"])
        assert payload["type"] == "event"
        assert payload["migration_id"] == migration_id
        assert payload["stage"] == stage
        assert payload["status"] == status
        assert payload["message"] == message
        assert "timestamp" in payload
        
        await pubsub.aclose()

    asyncio.run(run_test())
