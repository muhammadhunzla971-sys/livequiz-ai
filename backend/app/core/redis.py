import redis.asyncio as aioredis

from app.core.config import Settings


def make_redis(s: Settings) -> aioredis.Redis:
    """Redis client with a bounded pool that makes callers wait instead of failing.

    Managed Redis plans cap connections (often ~50). Without a bound, a busy room opens one
    connection per concurrent operation and the extra ones are refused; with a blocking pool
    the operation just queues for a free connection for a moment.
    """
    pool = aioredis.BlockingConnectionPool.from_url(
        s.redis_url,
        max_connections=s.redis_max_connections,
        timeout=s.redis_pool_wait_sec,
        decode_responses=True,
    )
    return aioredis.Redis(connection_pool=pool)
