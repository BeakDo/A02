from functools import lru_cache
from typing import List

from pydantic import BaseSettings, Field, HttpUrl, validator


class Settings(BaseSettings):
    app_name: str = "Upbit Order Block Trader"
    api_v1_prefix: str = "/api/v1"
    backend_cors_origins: List[HttpUrl] = Field(default_factory=list)
    upbit_rest_base: HttpUrl = Field(default="https://api.upbit.com")
    upbit_ws_url: HttpUrl = Field(default="wss://api.upbit.com/websocket/v1")
    symbols: List[str] = Field(default_factory=lambda: ["KRW-BTC", "KRW-ETH", "KRW-XRP", "KRW-SOL", "KRW-ADA"])
    max_position_weight: float = 1.5
    websocket_ping_interval: float = 20.0
    upbit_access_key: str | None = Field(default=None)
    upbit_secret_key: str | None = Field(default=None)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @validator("backend_cors_origins", pre=True)
    def assemble_cors_origins(cls, v):  # type: ignore
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i]
        return v


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
