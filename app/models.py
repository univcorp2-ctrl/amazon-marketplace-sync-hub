from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class ProductRecord(BaseModel):
    asin: str
    title: str
    brand: str | None = None
    price: float | None = None
    currency: str = "JPY"
    available: bool = False
    stock_quantity: int | None = None
    images: list[str] = Field(default_factory=list)
    identifiers: list[dict[str, Any]] = Field(default_factory=list)
    dimensions: list[dict[str, Any]] = Field(default_factory=list)
    categories: list[dict[str, Any]] = Field(default_factory=list)
    sales_ranks: list[dict[str, Any]] = Field(default_factory=list)
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
    summaries: list[dict[str, Any]] = Field(default_factory=list)
    raw_catalog: dict[str, Any] = Field(default_factory=dict)
    raw_pricing: dict[str, Any] = Field(default_factory=dict)
    raw_offers: dict[str, Any] = Field(default_factory=dict)
    fetched_at: str = Field(default_factory=utc_now_iso)
    source: str = "amazon-sp-api"
    availability_note: str = "Amazon retail exact quantity is not exposed; available is inferred from offer data."

    @field_validator("asin")
    @classmethod
    def validate_asin(cls, value: str) -> str:
        normalized = value.strip().upper()
        if len(normalized) != 10 or not normalized.isalnum():
            raise ValueError("ASIN must be 10 alphanumeric characters")
        return normalized


class ListingRequest(BaseModel):
    asin: str
    channels: list[Literal["shopee", "qoo10"]] = Field(default_factory=list)
    rights_confirmed: bool = False
    title: str | None = None
    description: str | None = None
    image_urls: list[str] = Field(default_factory=list)
    seller_sku: str | None = None
    shopee_category_id: int | None = None
    qoo10_category_id: str | None = None
    shipping_no: int | None = None

    @field_validator("channels")
    @classmethod
    def unique_channels(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))


class PriceRule(BaseModel):
    markup: float = 1.18
    fixed_fee: int = 300
    minimum_margin: int = 300


def calculate_target_price(source_price: float | None, rule: PriceRule) -> int:
    if source_price is None or source_price <= 0:
        raise ValueError("A positive Amazon price is required")
    raw = source_price * rule.markup + rule.fixed_fee
    floor = source_price + rule.minimum_margin
    rounded = int(max(raw, floor) + 9) // 10 * 10
    return max(1, rounded)
