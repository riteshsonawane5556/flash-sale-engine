from pydantic import BaseModel


class InitSaleRequest(BaseModel):
    name: str = "Product"
    units: int


class BuyRequest(BaseModel):
    user_id: str


class ConfirmRequest(BaseModel):
    user_id: str


class InitSaleResponse(BaseModel):
    product_id: str
    units: int
    stock: int


class BuyResponse(BaseModel):
    status: str
    stock: int
    position: int | None = None


class ConfirmResponse(BaseModel):
    status: str
    order_id: str | None = None


class StockResponse(BaseModel):
    product_id: str
    stock: int
    waitlist_len: int


class WaitlistPositionResponse(BaseModel):
    user_id: str
    product_id: str
    position: int | None
