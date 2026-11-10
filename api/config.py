import os
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./polonix.db"
    redis_url: str = "redis://localhost:6379"
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    admin_wallets: str = ""  # comma-separated wallet addresses

    class Config:
        env_file = (Path(__file__).resolve().parents[1] / ".env", ".env")


settings = Settings()