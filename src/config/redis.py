import redis.asyncio as aioredis
from src.config.settings import settings

_client: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=100,
        )
    return _client


async def get_pubsub_client() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url, decode_responses=True)


async def configure_keyspace_notifications(client: aioredis.Redis) -> None:
    await client.config_set("notify-keyspace-events", "Ex")


async def close_redis() -> None:
    global _client
    if _client:
        await _client.aclose()
        _client = None
