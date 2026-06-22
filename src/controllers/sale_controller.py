import asyncio
import json

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as aioredis

from src.config.settings import settings
from src.repositories.sale_repository import SaleRepository
from src.routes.sale_schema import (
    BuyRequest,
    BuyResponse,
    ConfirmRequest,
    ConfirmResponse,
    InitSaleRequest,
    InitSaleResponse,
    StockResponse,
    WaitlistPositionResponse,
)
from src.services.inventory_service import InventoryService
from src.services.waitlist_service import WaitlistService
from src.utils.helpers import stock_channel, stock_key
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SaleController:
    def __init__(self, redis_client: aioredis.Redis, session: AsyncSession):
        self._r = redis_client
        self._session = session
        self._inventory = InventoryService(redis_client)
        self._waitlist = WaitlistService(redis_client)
        self._repo = SaleRepository(session)

    async def init_sale(self, product_id: str, body: InitSaleRequest) -> InitSaleResponse:
        await self._repo.upsert_product(product_id, body.name, body.units)
        stock = await self._inventory.initialize_stock(product_id, body.units)
        return InitSaleResponse(product_id=product_id, units=body.units, stock=stock)

    async def buy(self, product_id: str, body: BuyRequest) -> BuyResponse:
        product = await self._repo.get_product(product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        reserved, stock = await self._inventory.buy(product_id, body.user_id)
        if reserved:
            return BuyResponse(status="reserved", stock=stock)

        position = await self._waitlist.join(product_id, body.user_id)
        return BuyResponse(status="waitlisted", stock=stock, position=position)

    async def confirm_payment(self, product_id: str, body: ConfirmRequest) -> ConfirmResponse:
        confirmed = await self._inventory.confirm_payment(product_id, body.user_id)
        if not confirmed:
            return ConfirmResponse(status="expired_or_invalid")

        order = await self._repo.create_order(product_id, body.user_id)
        return ConfirmResponse(status="confirmed", order_id=order.id)

    async def get_stock(self, product_id: str) -> StockResponse:
        stock = await self._inventory.get_stock(product_id)
        waitlist_len = await self._waitlist.length(product_id)
        return StockResponse(product_id=product_id, stock=stock, waitlist_len=waitlist_len)

    async def get_waitlist_position(self, product_id: str, user_id: str) -> WaitlistPositionResponse:
        position = await self._waitlist.position(product_id, user_id)
        return WaitlistPositionResponse(user_id=user_id, product_id=product_id, position=position)

    async def stream_stock(self, product_id: str) -> StreamingResponse:
        return StreamingResponse(
            self._sse_generator(product_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    async def _sse_generator(self, product_id: str):
        current = await self._inventory.get_stock(product_id)
        yield f"data: {json.dumps({'stock': current})}\n\n"

        pubsub_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        pubsub = pubsub_client.pubsub()
        await pubsub.subscribe(stock_channel(product_id))
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    stock_val = message["data"]
                    yield f"data: {json.dumps({'stock': int(stock_val)})}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe(stock_channel(product_id))
            await pubsub.aclose()
            await pubsub_client.aclose()
