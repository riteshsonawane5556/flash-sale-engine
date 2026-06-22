import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.config.db import init_db
from src.config.redis import close_redis, configure_keyspace_notifications, get_pubsub_client, get_redis
from src.routes.sale_routes import router as sale_router
from src.services.expiry_service import listen_for_expirations
from src.utils.logger import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)

_expiry_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _expiry_task

    await init_db()
    logger.info("database initialized")

    redis_client = await get_redis()
    await configure_keyspace_notifications(redis_client)
    logger.info("redis keyspace notifications configured")

    pubsub_client = await get_pubsub_client()
    _expiry_task = asyncio.create_task(listen_for_expirations(pubsub_client))
    logger.info("expiry listener started")

    yield

    if _expiry_task:
        _expiry_task.cancel()
        try:
            await _expiry_task
        except asyncio.CancelledError:
            pass

    await close_redis()
    await pubsub_client.aclose()
    logger.info("shutdown complete")


app = FastAPI(title="Flash Sale Engine", lifespan=lifespan)
app.include_router(sale_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
