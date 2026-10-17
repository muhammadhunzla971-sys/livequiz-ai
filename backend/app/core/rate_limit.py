from fastapi import HTTPException, status
from redis.asyncio import Redis


async def hit(redis: Redis, key: str, limit: int, window_sec: int) -> tuple[bool, int]:
    """Fixed-window counter. Returns (allowed, retry_after_seconds)."""
    full_key = f"rl:{key}"
    count = await redis.incr(full_key)
    if count == 1:
        await redis.expire(full_key, window_sec)
    if count > limit:
        ttl = await redis.ttl(full_key)
        return False, max(int(ttl), 1)
    return True, 0


async def enforce(redis: Redis, key: str, limit: int, window_sec: int) -> None:
    allowed, retry_after = await hit(redis, key, limit, window_sec)
    if not allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many requests, please slow down.",
            headers={"Retry-After": str(retry_after)},
        )
