import redis.asyncio as aioredis
from app.config.settings import settings

# Initialize the Redis connection pool using REDIS_URL from settings
redis_pool = aioredis.ConnectionPool.from_url(
    settings.REDIS_URL,
    decode_responses=True
)

# Global async Redis client instance
redis_client = aioredis.Redis(connection_pool=redis_pool)

def get_redis_client() -> aioredis.Redis:
    """
    Returns an async Redis client instance from the shared connection pool.
    Useful for FastAPI dependency injection.
    """
    return aioredis.Redis(connection_pool=redis_pool)
