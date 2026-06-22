import asyncio
import secrets
import time

import redis.asyncio as aioredis

from src.config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

RELEASE_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


def stock_key(product_id: str) -> str:
    return f"sale:{product_id}:stock"


def lock_key(product_id: str) -> str:
    return f"lock:sale:{product_id}"


def waitlist_key(product_id: str) -> str:
    return f"waitlist:{product_id}"


def reservation_key(product_id: str, user_id: str) -> str:
    return f"reservation:{product_id}:{user_id}"


def stock_channel(product_id: str) -> str:
    return f"stock:{product_id}"


def now_ms() -> int:
    return int(time.time() * 1000)


def parse_reservation_key(key: str) -> tuple[str, str] | None:
    parts = key.split(":")
    if len(parts) != 3 or parts[0] != "reservation":
        return None
    return parts[1], parts[2]


class DistributedLock:
    def __init__(self, client: aioredis.Redis, product_id: str):
        self._client = client
        self._key = lock_key(product_id)
        self._token: str | None = None

    async def acquire(self) -> bool:
        self._token = secrets.token_hex(16)
        for attempt in range(settings.lock_retry_attempts):
            result = await self._client.set(
                self._key,
                self._token,
                nx=True,
                px=settings.lock_ttl_ms,
            )
            if result:
                return True
            await asyncio.sleep(settings.lock_retry_delay_ms / 1000)
        return False

    async def release(self) -> None:
        if self._token:
            await self._client.eval(RELEASE_LUA, 1, self._key, self._token)
            self._token = None

    async def __aenter__(self) -> "DistributedLock":
        acquired = await self.acquire()
        if not acquired:
            raise TimeoutError(f"Could not acquire lock {self._key}")
        return self

    async def __aexit__(self, *_) -> None:
        await self.release()
