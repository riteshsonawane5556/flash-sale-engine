from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redis_url: str = "redis://localhost:6379/0"
    redis_db: int = 0
    database_url: str = "sqlite+aiosqlite:///./flash_sale.db"

    payment_ttl_ms: int = 600_000
    lock_ttl_ms: int = 5_000
    lock_retry_attempts: int = 10
    lock_retry_delay_ms: int = 100

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
