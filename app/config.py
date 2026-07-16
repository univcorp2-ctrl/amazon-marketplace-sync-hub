from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Amazon Marketplace Sync Hub"
    app_mode: str = "demo"
    api_live_enabled: bool = False
    enable_background_sync: bool = False
    database_url: str = "sqlite:///./data/app.db"
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])

    amazon_lwa_client_id: str = ""
    amazon_lwa_client_secret: str = ""
    amazon_refresh_token: str = ""
    amazon_sp_api_endpoint: str = "https://sellingpartnerapi-fe.amazon.com"
    amazon_marketplace_id: str = "A1VC38T7YXB528"
    amazon_cache_ttl_seconds: int = 300

    shopee_partner_id: int = 0
    shopee_partner_key: str = ""
    shopee_shop_id: int = 0
    shopee_access_token: str = ""
    shopee_base_url: str = "https://partner.shopeemobile.com"
    shopee_default_category_id: int = 0
    shopee_logistic_info: list[dict[str, Any]] = Field(default_factory=list)

    qoo10_api_key: str = ""
    qoo10_user_id: str = ""
    qoo10_password: str = ""
    qoo10_base_url: str = "https://api.qoo10.jp"
    qoo10_default_category_id: str = ""
    qoo10_shipping_no: int = 0
    qoo10_contact_tel: str = ""
    qoo10_production_place: str = "Japan"

    price_markup: float = 1.18
    price_fixed_fee: int = 300
    minimum_margin: int = 300
    stock_buffer_quantity: int = 2
    sync_interval_seconds: int = 900
    rights_confirmation_required: bool = True

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
