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

# MockRedis definition for local in-memory simulation when Redis is not running
class MockRedis:
    def __init__(self):
        self.lists = {}
        self.pubsub_channels = {}

    async def ping(self):
        return True

    async def delete(self, *keys):
        for key in keys:
            self.lists.pop(key, None)

    async def keys(self, pattern):
        import fnmatch
        return [k for k in self.lists.keys() if fnmatch.fnmatch(k, pattern)]

    async def lpush(self, key, value):
        if key not in self.lists:
            self.lists[key] = []
        self.lists[key].insert(0, value)
        return len(self.lists[key])

    async def brpop(self, key, timeout=0):
        if key not in self.lists or not self.lists[key]:
            if timeout > 0:
                await asyncio.sleep(min(timeout, 0.1))
            if key not in self.lists or not self.lists[key]:
                return None
        val = self.lists[key].pop()
        return (key, val)

    async def lrange(self, key, start, end):
        if key not in self.lists:
            return []
        if end == -1:
            return self.lists[key][start:]
        return self.lists[key][start:end+1]

    async def lrem(self, key, count, value):
        if key not in self.lists:
            return 0
        original_len = len(self.lists[key])
        self.lists[key] = [v for v in self.lists[key] if v != value]
        return original_len - len(self.lists[key])

    async def publish(self, channel, message):
        if channel in self.pubsub_channels:
            count = 0
            for queue in self.pubsub_channels[channel]:
                await queue.put({"type": "message", "channel": channel, "data": message})
                count += 1
            return count
        return 0

    async def set(self, key, value):
        self.lists[key] = value
        return True

    async def get(self, key):
        return self.lists.get(key)

    def pubsub(self):
        return MockPubSub(self)

class MockPubSub:
    def __init__(self, client):
        self.client = client
        self.channels = []
        self.queue = asyncio.Queue()

    async def subscribe(self, channel):
        self.channels.append(channel)
        if channel not in self.client.pubsub_channels:
            self.client.pubsub_channels[channel] = []
        self.client.pubsub_channels[channel].append(self.queue)

    async def get_message(self, ignore_subscribe_messages=False, timeout=0):
        try:
            if timeout > 0:
                return await asyncio.wait_for(self.queue.get(), timeout=timeout)
            return self.queue.get_nowait()
        except (asyncio.QueueEmpty, asyncio.TimeoutError):
            return None

    async def unsubscribe(self, channel=None):
        pass

    async def aclose(self):
        pass


@pytest.fixture
def redis_integration_client():
    """Initializes the Redis client for integration testing with MockRedis fallback."""
    client = aioredis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        # Check if real Redis is available
        asyncio.run(client.ping())
        yield client
        asyncio.run(client.aclose())
    except Exception:
        # Fallback to local MockRedis
        mock_client = MockRedis()
        app.redis.client.redis_client = mock_client
        app.redis.manager.redis_client = mock_client
        app.redis.publisher.redis_client = mock_client
        app.redis.subscriber.redis_client = mock_client
        yield mock_client


@pytest.fixture(autouse=True)
def clean_redis_keys(redis_integration_client):
    """Ensures Redis namespace is clean before and after integration tests."""
    async def _clean():
        await redis_integration_client.delete("hipforge:queue:pending", "hipforge:queue:active")
        if hasattr(redis_integration_client, "keys"):
            keys = await redis_integration_client.keys("migration:*")
            if keys:
                await redis_integration_client.delete(*keys)
    asyncio.run(_clean())
    yield
    asyncio.run(_clean())


def test_migration_worker_integration(redis_integration_client):
    """
    Integration test for the Migration Worker:
    1. Starts worker in a background thread.
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
        # compilation succeeds only after RESEARCHING stage completes (setting researched to True)
        if getattr(context, "researched", False):
            context.compilation_success = True
        else:
            context.compilation_success = False
            
    app.workflow_engine.states.handle_compiling = mock_handle_compiling
    
    try:
        # Start worker loop in a background thread
        worker_loop = asyncio.new_event_loop()
        def worker_target():
            asyncio.set_event_loop(worker_loop)
            worker_loop.run_until_complete(run_worker())
            
        thread = threading.Thread(target=worker_target, daemon=True)
        app.workers.migration_worker.running = True
        thread.start()
        
        # Wait briefly for thread initiation
        time.sleep(0.3)
        assert thread.is_alive(), "Worker thread must start successfully"
        
        migration_id = "int-test-job-123"
        payload = {
            "migration_id": migration_id,
            "workspace_path": "/app/workspace/int-test-123",
            "retry_budget": 1  # Ensures loop goes: QUEUED -> PREPARING -> HIPIFY -> SCA -> COMPILING (fail) -> ANALYZING -> PATCHING -> COMPILING (fail) -> RESEARCHING -> COMPILING (success) -> GENERATING_REPORT -> COMPLETED
        }
        
        # Subscribe to Pub/Sub events channel to capture all transition events
        pubsub = redis_integration_client.pubsub()
        asyncio.run(pubsub.subscribe(events_channel(migration_id)))
        
        # Push the job into Redis pending queue
        async def submit_job():
            from app.redis.manager import enqueue_job
            await enqueue_job(migration_id, payload)
        asyncio.run(submit_job())
        
        # Wait for the job status to transition to COMPLETED (with timeout)
        timeout = 5.0
        start_time = time.time()
        completed = False
        
        while time.time() - start_time < timeout:
            async def get_status():
                return await redis_integration_client.get(status_key(migration_id))
            status = asyncio.run(get_status())
            if status == "COMPLETED":
                completed = True
                break
            time.sleep(0.1)
            
        assert completed, f"Job failed to reach COMPLETED state. Last status: {asyncio.run(get_status()) if 'get_status' in locals() else 'None'}"
        
        # Retrieve and parse all published Pub/Sub transition events
        events_collected = []
        async def collect_events():
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.01)
                if msg is None:
                    break
                events_collected.append(json.loads(msg["data"]))
            await pubsub.aclose()
        asyncio.run(collect_events())
        
        # Assert all 10 stages were traversed and published
        expected_stages = {
            "QUEUED", "PREPARING", "HIPIFY", "SCA", "COMPILING",
            "ANALYZING", "PATCHING", "RESEARCHING", "GENERATING_REPORT", "COMPLETED"
        }
        
        stages_published = {evt.get("stage") for evt in events_collected if evt.get("stage")}
        for stage in expected_stages:
            assert stage in stages_published, f"Stage {stage} was not executed or published"
            
        # Assert worker remains alive and running after task completion
        assert thread.is_alive(), "Worker thread crashed or stopped unexpectedly after task completion"
        
        # Graceful shutdown of the worker thread
        app.workers.migration_worker.running = False
        thread.join(timeout=2.0)
        
    finally:
        # Cleanup mock handlers
        app.workflow_engine.states.handle_compiling = original_handle_compiling
        if "MIGRATION_WORKER_TIMEOUT" in os.environ:
            del os.environ["MIGRATION_WORKER_TIMEOUT"]
