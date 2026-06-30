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

@pytest.fixture(scope="session")
def redis_test_client():
    """
    Initializes the Redis client for testing. 
    Attempts connecting to settings.REDIS_URL, falling back to a mock client simulator if unavailable.
    """
    client = aioredis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        asyncio.run(client.ping())
        yield client
        asyncio.run(client.aclose())
    except Exception:
        # Fallback to local mock simulator
        mock_client = MockRedis()
        app.redis.client.redis_client = mock_client
        app.redis.manager.redis_client = mock_client
        app.redis.publisher.redis_client = mock_client
        app.redis.subscriber.redis_client = mock_client
        yield mock_client

@pytest.fixture(autouse=True)
def clean_redis(redis_test_client):
    """Automatically cleans keys before each test execution."""
    async def _clean():
        await redis_test_client.delete("hipforge:queue:pending", "hipforge:queue:active")
        keys = await redis_test_client.keys("migration:*")
        if keys:
            await redis_test_client.delete(*keys)
    asyncio.run(_clean())
    yield
