import os
import sys
import json
import time
import asyncio
import threading
import pytest
import redis.asyncio as aioredis

# Ensure backend directory is in python path
sys.path.insert(0, "backend")

from app.config.settings import settings
import app.redis.client
import app.redis.manager
import app.redis.publisher
import app.redis.subscriber
from app.workers.migration_worker import run_worker
import app.workers.migration_worker
from app.redis.keys import status_key, events_channel

from tests.conftest import MockRedis


@pytest.fixture
def redis_integration_client():
    """Initializes the Redis client for integration testing with MockRedis fallback."""
    # Save originals so we can restore them after the test
    orig_client = app.redis.client.redis_client
    orig_manager = app.redis.manager.redis_client
    orig_publisher = app.redis.publisher.redis_client
    orig_subscriber = app.redis.subscriber.redis_client

    is_live = False
    temp_client = aioredis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        # Check if real Redis is available
        asyncio.run(temp_client.ping())
        asyncio.run(temp_client.aclose())
        result_client = aioredis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        is_live = True
    except Exception:
        # Fallback to local MockRedis
        result_client = MockRedis()

    # Always patch app modules with the chosen client
    app.redis.client.redis_client = result_client
    app.redis.manager.redis_client = result_client
    app.redis.publisher.redis_client = result_client
    app.redis.subscriber.redis_client = result_client

    yield result_client

    # Restore originals
    app.redis.client.redis_client = orig_client
    app.redis.manager.redis_client = orig_manager
    app.redis.publisher.redis_client = orig_publisher
    app.redis.subscriber.redis_client = orig_subscriber

    if is_live:
        try:
            asyncio.run(result_client.aclose())
        except RuntimeError:
            pass


@pytest.fixture(autouse=True)
def clean_redis_keys():
    """Ensures Redis namespace is clean before and after integration tests."""
    async def _clean():
        client = aioredis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            await client.delete("hipforge:queue:pending", "hipforge:queue:active")
            keys = await client.keys("migration:*")
            if keys:
                await client.delete(*keys)
        except Exception:
            # Fallback: clean mock client in memory databases
            from app.redis.client import redis_client
            if hasattr(redis_client, "db"):
                redis_client.db.clear()
            if hasattr(redis_client, "lists"):
                redis_client.lists.clear()
            if hasattr(redis_client, "_db"):
                redis_client._db.clear()
            if hasattr(redis_client, "_lists"):
                redis_client._lists.clear()
        finally:
            await client.aclose()
            
    asyncio.run(_clean())
    yield
    asyncio.run(_clean())


@pytest.mark.anyio
async def test_migration_worker_integration(redis_integration_client):
    """
    Integration test for the Migration Worker:
    1. Starts worker in a background asyncio task.
    2. Submits a job via Redis LPUSH.
    3. Asserts the job successfully transitions through all 10 states to reach COMPLETED.
    4. Asserts that the worker remains alive after job execution.
    """
    # Configure fast timeout check for the worker loop
    os.environ["MIGRATION_WORKER_TIMEOUT"] = "1"
    
    # Mock compile behavior to fail compiled attempts until the Research phase completes
    import app.workflow_engine.states
    original_handle_compiling = app.workflow_engine.states.handle_compiling
    
    async def mock_handle_compiling(context):
        # compilation succeeds on attempt 1
        if context.current_attempt > 0:
            context.compilation_success = True
        else:
            context.compilation_success = False
            
    app.workflow_engine.states.handle_compiling = mock_handle_compiling
    
    from app.redis.client import redis_client
    migration_id = "int-test-job-123"
    payload = {
        "migration_id": migration_id,
        "workspace_path": "/app/workspace/int-test-123",
        "retry_budget": 1  # Ensures loop goes through PREFLIGHT before HIPIFY.
    }
    
    # Start the worker in the background as an asyncio Task
    app.workers.migration_worker.running = True
    worker_task = asyncio.create_task(run_worker())
    
    try:
        # Subscribe to Pub/Sub events channel to capture all transition events
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(events_channel(migration_id))
        
        # Push the job into Redis pending queue
        from app.redis.keys import pending_queue_key
        import json
        await redis_client.lpush(pending_queue_key(), json.dumps({"migration_id": migration_id, **payload}))
        
        # Wait for the job status to transition to COMPLETED (with timeout)
        timeout = 5.0
        start_time = time.time()
        completed = False
        
        while time.time() - start_time < timeout:
            status = await redis_client.get(status_key(migration_id))
            if status == "COMPLETED":
                completed = True
                break
            await asyncio.sleep(0.1)
            
        assert completed, f"Job failed to reach COMPLETED state. Last status: {await redis_client.get(status_key(migration_id))}"
        
        # Retrieve and parse all published Pub/Sub transition events
        events_collected = []
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.01)
            if msg is None:
                break
            events_collected.append(json.loads(msg["data"]))
        await pubsub.aclose()
        
        # Assert all 10 stages were traversed and published
        expected_stages = {
            "QUEUED", "PREPARING", "PREFLIGHT", "HIPIFY", "SCA", "COMPILING",
            "ANALYZING", "PATCHING", "GENERATING_REPORT", "COMPLETED"
        }
        
        stages_published = {evt.get("stage") for evt in events_collected if evt.get("stage")}
        for stage in expected_stages:
            assert stage in stages_published, f"Stage {stage} was not executed or published"
            
        # Assert worker remains alive and running after task completion
        assert not worker_task.done(), "Worker task died unexpectedly"
        
    finally:
        # Graceful shutdown of the worker task
        app.workers.migration_worker.running = False
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
            
        # Cleanup mock handlers
        app.workflow_engine.states.handle_compiling = original_handle_compiling
        if "MIGRATION_WORKER_TIMEOUT" in os.environ:
            del os.environ["MIGRATION_WORKER_TIMEOUT"]
