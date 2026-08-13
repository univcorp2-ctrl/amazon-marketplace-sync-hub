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
    api_admin_key: str = ""
    database_url: str = "sqlite:///./data/app.db"
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])

    amazon_lwa_client_id: str = ""
    amazon_lwa_client_secret: str = ""
    amazon_refresh_token: str = ""
    amazon_sp_api_endpoint: str = "https://sellingpartnerapi-fe.amazon.com"
    amazon_marketplace_id: str = "A1VC38T7YXB528"
    amazon_cache_ttl_seconds: int = 300
    amazon_search_page_size: int = 10
    amazon_search_max_pages: int = 1
    amazon_max_retries: int = 3

    shopee_partner_id: int = 0
    shopee_partner_key: str = ""
    shopee_shop_id: int = 0
    shopee_access_token: str = ""
    shopee_base_url: str = "https://partner.shopeemobile.com"
    shopee_default_category_id: int = 0
    shopee_logistic_info: list[dict[str, Any]] = Field(default_factory=list)
    shopee_market: str = ""
    shopee_request_interval_seconds: float = 1.5
    shopee_max_retries: int = 3
    shopee_max_calls_per_process: int = 120
    shopee_max_images_per_listing: int = 4
    shopee_blacklist_path: str = "data/shopee_blacklist.json"
    shopee_policy_strict: bool = True

    bulk_listing_enabled: bool = False
    bulk_listing_per_run_cap: int = 5
    bulk_listing_daily_cap: int = 20
    bulk_listing_delay_seconds: float = 8.0
    bulk_listing_stop_after_errors: int = 2

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

    def live_readiness(self) -> dict[str, bool]:
        amazon_configured = bool(self.amazon_lwa_client_id.strip() and self.amazon_lwa_client_secret.strip() and self.amazon_refresh_token.strip() and self.amazon_marketplace_id.strip())
        shopee_configured = bool(self.shopee_partner_id > 0 and self.shopee_partner_key.strip() and self.shopee_shop_id > 0 and self.shopee_access_token.strip())
        shopee_listing_defaults = bool(self.shopee_default_category_id > 0 and self.shopee_logistic_info)
        return {
            "runtime_live": self.app_mode == "production" and self.api_live_enabled,
            "admin_auth": len(self.api_admin_key) >= 32,
            "cors_restricted": bool(self.cors_origins) and "*" not in self.cors_origins,
            "amazon_configured": amazon_configured,
            "shopee_configured": shopee_configured,
            "shopee_listing_defaults": shopee_listing_defaults,
            "rights_gate_enabled": self.rights_confirmation_required,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
