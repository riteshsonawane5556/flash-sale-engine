from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as aioredis

from src.config.db import get_db
from src.config.redis import get_redis
from src.controllers.sale_controller import SaleController
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

router = APIRouter(prefix="/sale", tags=["sale"])


def get_controller(
    redis_client: aioredis.Redis = Depends(get_redis),
    session: AsyncSession = Depends(get_db),
) -> SaleController:
    return SaleController(redis_client, session)


@router.post("/{product_id}/init", response_model=InitSaleResponse)
async def init_sale(
    product_id: str,
    body: InitSaleRequest,
    controller: SaleController = Depends(get_controller),
):
    return await controller.init_sale(product_id, body)


@router.post("/{product_id}/buy", response_model=BuyResponse)
async def buy(
    product_id: str,
    body: BuyRequest,
    controller: SaleController = Depends(get_controller),
):
    return await controller.buy(product_id, body)


@router.post("/{product_id}/confirm", response_model=ConfirmResponse)
async def confirm_payment(
    product_id: str,
    body: ConfirmRequest,
    controller: SaleController = Depends(get_controller),
):
    return await controller.confirm_payment(product_id, body)


@router.get("/{product_id}/stock", response_model=StockResponse)
async def get_stock(
    product_id: str,
    controller: SaleController = Depends(get_controller),
):
    return await controller.get_stock(product_id)


@router.get("/{product_id}/waitlist/{user_id}", response_model=WaitlistPositionResponse)
async def get_waitlist_position(
    product_id: str,
    user_id: str,
    controller: SaleController = Depends(get_controller),
):
    return await controller.get_waitlist_position(product_id, user_id)


@router.get("/{product_id}/stream")
async def stream_stock(
    product_id: str,
    controller: SaleController = Depends(get_controller),
):
    return await controller.stream_stock(product_id)
