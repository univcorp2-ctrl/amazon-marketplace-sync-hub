from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlparse

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
    availability_note: str = (
        "Amazon retail exact quantity is not exposed; available is inferred from offer data."
    )

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
    title: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, min_length=1, max_length=5000)
    image_urls: list[str] = Field(default_factory=list, max_length=9)
    seller_sku: str | None = Field(default=None, max_length=64)
    shopee_category_id: int | None = Field(default=None, gt=0)
    shopee_attributes: list[dict[str, Any]] = Field(default_factory=list)
    qoo10_category_id: str | None = None
    shipping_no: int | None = Field(default=None, gt=0)
    price_override: int | None = Field(default=None, gt=0)
    stock_override: int | None = Field(default=None, ge=0, le=100)
    package_weight_kg: float | None = Field(default=None, gt=0)
    package_length_cm: float | None = Field(default=None, gt=0)
    package_width_cm: float | None = Field(default=None, gt=0)
    package_height_cm: float | None = Field(default=None, gt=0)
    preorder_days: int = Field(default=2, ge=2, le=30)
    force_relist: bool = False

    @field_validator("channels")
    @classmethod
    def unique_channels(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))

    @field_validator("image_urls")
    @classmethod
    def validate_image_urls(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for raw in value:
            url = raw.strip()
            parsed = urlparse(url)
            if parsed.scheme != "https" or not parsed.hostname:
                raise ValueError("Every image URL must be an absolute HTTPS URL")
            normalized.append(url)
        return list(dict.fromkeys(normalized))

    @field_validator("seller_sku")
    @classmethod
    def normalize_sku(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if any(character.isspace() for character in normalized):
            raise ValueError("seller_sku must not contain whitespace")
        return normalized


class PriceRule(BaseModel):
    """Pricing rule. Additive values are denominated in the target currency."""

    markup: float = 1.18
    fixed_fee: int = 300
    minimum_margin: int = 300
    fx_rate: float = 1.0
    marketplace_fee_rate: float = 0.0
    shipping_cost: int = 0
    rounding_step: int = 10


def calculate_target_price(source_price: float | None, rule: PriceRule) -> int:
    if source_price is None or source_price <= 0:
        raise ValueError("A positive Amazon price is required")
    if rule.fx_rate <= 0 or rule.rounding_step <= 0:
        raise ValueError("FX rate and rounding step must be positive")
    if not 0 <= rule.marketplace_fee_rate < 1:
        raise ValueError("Marketplace fee rate must be at least 0 and below 1")

    converted_cost = source_price * rule.fx_rate
    fee_multiplier = 1 - rule.marketplace_fee_rate
    markup_price = (
        converted_cost * rule.markup + rule.fixed_fee + rule.shipping_cost
    ) / fee_multiplier
    margin_floor = (
        converted_cost + rule.minimum_margin + rule.shipping_cost
    ) / fee_multiplier
    required = max(markup_price, margin_floor)
    rounded = math.ceil(required / rule.rounding_step) * rule.rounding_step
    return max(1, int(rounded))
