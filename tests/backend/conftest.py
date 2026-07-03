import pytest
import asyncio
import redis.asyncio as aioredis
from app.config.settings import settings
import app.redis.client
import app.redis.manager
import app.redis.publisher
import app.redis.subscriber

class MockRedis:
    """In-memory Redis simulator to facilitate local testing when no live Redis server is running."""
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

    def pubsub(self):
        return MockPubSub(self)

class MockPubSub:
    """Mock PubSub connection matching redis-py PubSub interface."""
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

@pytest.fixture(scope="function")
def redis_test_client():
    """
    Initializes the Redis client for testing.
    Attempts connecting to settings.REDIS_URL, falling back to a mock client simulator if unavailable.
    Always patches app.redis.* modules so async tests use the correct client.
    """
    # Save originals so we can restore them after the test
    orig_client = app.redis.client.redis_client
    orig_manager = app.redis.manager.redis_client
    orig_publisher = app.redis.publisher.redis_client
    orig_subscriber = app.redis.subscriber.redis_client

    is_live = False
    temp_client = aioredis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        asyncio.run(temp_client.ping())
        asyncio.run(temp_client.aclose())
        result_client = aioredis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        is_live = True
    except Exception:
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
            # Event loop already closed after an async test — connection will be GC'd
            pass

@pytest.fixture(autouse=True)
def clean_redis():
    """Automatically cleans keys before each test execution."""
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
            if hasattr(redis_client, "lists") and isinstance(redis_client.lists, dict):
                redis_client.lists.clear()
            if hasattr(redis_client, "pubsub_channels") and isinstance(redis_client.pubsub_channels, dict):
                redis_client.pubsub_channels.clear()
        finally:
            await client.aclose()
            
    asyncio.run(_clean())
    yield

