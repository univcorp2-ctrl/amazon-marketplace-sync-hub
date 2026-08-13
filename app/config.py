from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

CsvList = Annotated[list[str], NoDecode]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Amazon Marketplace Sync Hub"
    app_mode: str = "demo"
    api_live_enabled: bool = False
    enable_background_sync: bool = False
    enable_docs: bool = False
    app_api_token: str = ""
    database_url: str = "sqlite:///./data/app.db"
    cors_origins: CsvList = Field(default_factory=lambda: ["*"])
    enabled_channels: CsvList = Field(default_factory=lambda: ["shopee"])

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
    shopee_refresh_token: str = ""
    shopee_token_state_file: str = ""
    shopee_base_url: str = "https://partner.shopeemobile.com"
    shopee_default_category_id: int = 0
    shopee_logistic_info: list[dict[str, Any]] = Field(default_factory=list)
    shopee_max_image_bytes: int = 10_000_000
    image_host_allowlist: CsvList = Field(default_factory=list)

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
    source_to_target_fx_rate: float = 1.0
    target_currency: str = "JPY"
    marketplace_fee_rate: float = 0.0
    shipping_cost: int = 0
    price_rounding_step: int = 10
    stock_buffer_quantity: int = 1
    sync_interval_seconds: int = 900
    rights_confirmation_required: bool = True
    allow_source_content_reuse: bool = False

    default_package_weight_kg: float = 0.8
    default_package_length_cm: float = 30
    default_package_width_cm: float = 20
    default_package_height_cm: float = 10

    @field_validator("cors_origins", "enabled_channels", "image_host_allowlist", mode="before")
    @classmethod
    def parse_csv_list(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("app_mode")
    @classmethod
    def validate_mode(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"demo", "production", "test"}:
            raise ValueError("APP_MODE must be demo, production, or test")
        return normalized

    @field_validator("enabled_channels")
    @classmethod
    def validate_channels(cls, value: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(item.strip().lower() for item in value))
        unsupported = sorted(set(normalized) - {"shopee", "qoo10"})
        if unsupported:
            raise ValueError(f"Unsupported channels: {', '.join(unsupported)}")
        return normalized

    @field_validator("marketplace_fee_rate")
    @classmethod
    def validate_fee_rate(cls, value: float) -> float:
        if not 0 <= value < 1:
            raise ValueError("MARKETPLACE_FEE_RATE must be at least 0 and below 1")
        return value

    @field_validator("source_to_target_fx_rate", "price_markup", "price_rounding_step")
    @classmethod
    def validate_positive_numbers(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("Pricing multipliers and rounding step must be positive")
        return value

    @property
    def is_production(self) -> bool:
        return self.app_mode == "production"

    def production_configuration_issues(self, *, include_api_token: bool = True) -> list[str]:
        if not self.is_production:
            return []

        issues: list[str] = []
        if not self.api_live_enabled:
            issues.append("API_LIVE_ENABLED")
        for name, value in (
            ("AMAZON_LWA_CLIENT_ID", self.amazon_lwa_client_id),
            ("AMAZON_LWA_CLIENT_SECRET", self.amazon_lwa_client_secret),
            ("AMAZON_REFRESH_TOKEN", self.amazon_refresh_token),
        ):
            if not value:
                issues.append(name)

        if "shopee" in self.enabled_channels:
            for name, value in (
                ("SHOPEE_PARTNER_ID", self.shopee_partner_id),
                ("SHOPEE_PARTNER_KEY", self.shopee_partner_key),
                ("SHOPEE_SHOP_ID", self.shopee_shop_id),
            ):
                if not value:
                    issues.append(name)
            if not (self.shopee_access_token or self.shopee_refresh_token):
                issues.append("SHOPEE_ACCESS_TOKEN or SHOPEE_REFRESH_TOKEN")
            if self.shopee_refresh_token and not self.shopee_token_state_file.strip():
                issues.append("SHOPEE_TOKEN_STATE_FILE (required with refresh token)")
            if self.enable_background_sync and not self.shopee_refresh_token:
                issues.append("SHOPEE_REFRESH_TOKEN (required for background sync)")

        if include_api_token and len(self.app_api_token) < 32:
            issues.append("APP_API_TOKEN (minimum 32 characters)")
        if "*" in self.cors_origins:
            issues.append("CORS_ORIGINS (wildcard is not allowed in production)")
        return issues

    def listing_configuration_issues(self, channel: str) -> list[str]:
        issues: list[str] = []
        if channel == "shopee":
            if not self.shopee_default_category_id:
                issues.append("SHOPEE_DEFAULT_CATEGORY_ID or request shopee_category_id")
            if not self.shopee_logistic_info:
                issues.append("SHOPEE_LOGISTIC_INFO")
            if self.is_production and not self.image_host_allowlist:
                issues.append("IMAGE_HOST_ALLOWLIST")
        elif channel == "qoo10":
            if not self.qoo10_default_category_id:
                issues.append("QOO10_DEFAULT_CATEGORY_ID or request qoo10_category_id")
            if not self.qoo10_shipping_no:
                issues.append("QOO10_SHIPPING_NO or request shipping_no")
        return issues


@lru_cache
def get_settings() -> Settings:
    return Settings()
