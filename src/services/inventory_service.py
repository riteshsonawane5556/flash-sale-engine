import redis.asyncio as aioredis

from src.config.settings import settings
from src.utils.helpers import (
    BUY_LUA,
    DistributedLock,
    reservation_key,
    stock_channel,
    stock_key,
    waitlist_key,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


class InventoryService:
    def __init__(self, client: aioredis.Redis):
        self._r = client

    async def initialize_stock(self, product_id: str, units: int) -> int:
        await self._r.set(stock_key(product_id), units)
        await self.publish_stock(product_id)
        return units

    async def get_stock(self, product_id: str) -> int:
        val = await self._r.get(stock_key(product_id))
        return int(val) if val is not None else 0

    async def buy(self, product_id: str, user_id: str) -> tuple[bool, int]:
        sk = stock_key(product_id)
        new_stock = await self._r.eval(BUY_LUA, 1, sk)

        if new_stock >= 0:
            res_key = reservation_key(product_id, user_id)
            await self._r.set(res_key, "pending", px=settings.payment_ttl_ms)
            await self.publish_stock(product_id)
            logger.info("reserved product=%s user=%s stock_remaining=%d", product_id, user_id, new_stock)
            return True, new_stock
        else:
            current = await self.get_stock(product_id)
            logger.info("out_of_stock product=%s user=%s", product_id, user_id)
            return False, current

    async def confirm_payment(self, product_id: str, user_id: str) -> bool:
        res_key = reservation_key(product_id, user_id)
        async with DistributedLock(self._r, product_id):
            exists = await self._r.exists(res_key)
            if not exists:
                return False
            await self._r.delete(res_key)
            return True

    async def restock_and_promote(self, product_id: str, expired_user_id: str) -> str | None:
        from src.services.waitlist_service import WaitlistService

        waitlist_svc = WaitlistService(self._r)
        async with DistributedLock(self._r, product_id):
            await self._r.incr(stock_key(product_id))
            logger.info("restocked product=%s expired_user=%s", product_id, expired_user_id)

            next_user = await waitlist_svc.pop_next(product_id)
            if next_user:
                new_stock = await self._r.decr(stock_key(product_id))
                res_key = reservation_key(product_id, next_user)
                await self._r.set(res_key, "pending", px=settings.payment_ttl_ms)
                logger.info("promoted user=%s product=%s stock=%d", next_user, product_id, new_stock)

            await self.publish_stock(product_id)
            return next_user

    async def publish_stock(self, product_id: str) -> None:
        current = await self.get_stock(product_id)
        channel = stock_channel(product_id)
        await self._r.publish(channel, str(current))
