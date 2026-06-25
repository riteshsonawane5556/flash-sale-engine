import asyncio

import redis.asyncio as aioredis

from src.config.settings import settings
from src.utils.helpers import parse_reservation_key
from src.utils.logger import get_logger

logger = get_logger(__name__)

KEYSPACE_CHANNEL = f"__keyevent@{settings.redis_db}__:expired"


async def listen_for_expirations(pubsub_client: aioredis.Redis, redis_client: aioredis.Redis) -> None:
    from src.services.inventory_service import InventoryService

    pubsub = pubsub_client.pubsub()
    await pubsub.subscribe(KEYSPACE_CHANNEL)
    logger.info("expiry_service listening on %s", KEYSPACE_CHANNEL)

    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message is None:
                await asyncio.sleep(0.1)
                continue

            if message["type"] != "message":
                continue

            expired_key: str = message["data"]
            parsed = parse_reservation_key(expired_key)
            if parsed is None:
                continue

            product_id, user_id = parsed
            logger.info("reservation_expired product=%s user=%s", product_id, user_id)

            try:
                inventory_svc = InventoryService(redis_client)
                promoted_user = await inventory_svc.restock_and_promote(product_id, user_id)
                if promoted_user:
                    logger.info("waitlist_promotion product=%s promoted_user=%s", product_id, promoted_user)
            except Exception as exc:
                logger.error("expiry_handler_error product=%s user=%s error=%s", product_id, user_id, exc)
    except asyncio.CancelledError:
        logger.info("expiry_service shutting down")
        await pubsub.unsubscribe(KEYSPACE_CHANNEL)
        await pubsub.aclose()
