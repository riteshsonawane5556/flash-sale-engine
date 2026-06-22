import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, DateTime, select
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.db import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    total_units: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    product_id: Mapped[str] = mapped_column(String, nullable=False)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="confirmed")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class SaleRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def upsert_product(self, product_id: str, name: str, total_units: int) -> Product:
        result = await self._session.execute(select(Product).where(Product.id == product_id))
        product = result.scalar_one_or_none()
        if product:
            product.total_units = total_units
            product.name = name
        else:
            product = Product(id=product_id, name=name, total_units=total_units)
            self._session.add(product)
        await self._session.commit()
        await self._session.refresh(product)
        return product

    async def get_product(self, product_id: str) -> Product | None:
        result = await self._session.execute(select(Product).where(Product.id == product_id))
        return result.scalar_one_or_none()

    async def create_order(self, product_id: str, user_id: str) -> Order:
        order = Order(
            id=str(uuid.uuid4()),
            product_id=product_id,
            user_id=user_id,
            status="confirmed",
        )
        self._session.add(order)
        await self._session.commit()
        await self._session.refresh(order)
        return order
