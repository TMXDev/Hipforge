import pytest
import asyncio
import redis.asyncio as aioredis
from app.config.settings import settings
import app.redis.client

from tests.conftest import MockRedis

@pytest.fixture(scope="function")
def redis_test_client():
    """
    Initializes the Redis client for testing.
    Attempts connecting to settings.REDIS_URL, falling back to a mock client simulator if unavailable.
    Always patches app.redis.* modules so async tests use the correct client.
    """
    # Save originals so we can restore them after the test
    orig_client = app.redis.client.redis_client

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

    yield result_client

    # Restore originals
    app.redis.client.redis_client = orig_client

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

