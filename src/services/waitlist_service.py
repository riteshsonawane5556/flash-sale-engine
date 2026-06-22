import redis.asyncio as aioredis

from src.utils.helpers import now_ms, waitlist_key
from src.utils.logger import get_logger

logger = get_logger(__name__)


class WaitlistService:
    def __init__(self, client: aioredis.Redis):
        self._r = client

    async def join(self, product_id: str, user_id: str) -> int:
        wk = waitlist_key(product_id)
        score = now_ms()
        await self._r.zadd(wk, {user_id: score}, nx=True)
        position = await self._r.zrank(wk, user_id)
        logger.info("waitlisted user=%s product=%s position=%s", user_id, product_id, position)
        return int(position) + 1 if position is not None else 1

    async def position(self, product_id: str, user_id: str) -> int | None:
        wk = waitlist_key(product_id)
        rank = await self._r.zrank(wk, user_id)
        if rank is None:
            return None
        return int(rank) + 1

    async def length(self, product_id: str) -> int:
        return await self._r.zcard(waitlist_key(product_id))

    async def pop_next(self, product_id: str) -> str | None:
        wk = waitlist_key(product_id)
        result = await self._r.zpopmin(wk, 1)
        if result:
            return result[0][0]
        return None
