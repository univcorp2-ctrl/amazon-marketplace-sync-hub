from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from app.config import Settings
from app.models import ProductRecord


class AsyncRateLimiter:
    def __init__(self, interval_seconds: float) -> None:
        self.interval = interval_seconds
        self._next = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            delay = self._next - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            self._next = time.monotonic() + self.interval


class AmazonSPAPIClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.client = client or httpx.AsyncClient(timeout=30)
        self._token: str | None = None
        self._token_expires_at = 0.0
        self.catalog_limiter = AsyncRateLimiter(0.55)
        self.pricing_limiter = AsyncRateLimiter(30.5)
        self.offers_limiter = AsyncRateLimiter(2.1)

    async def close(self) -> None:
        await self.client.aclose()

    async def _access_token(self) -> str:
        if self._token and time.monotonic() < self._token_expires_at - 60:
            return self._token
        required = [
            self.settings.amazon_lwa_client_id,
            self.settings.amazon_lwa_client_secret,
            self.settings.amazon_refresh_token,
        ]
        if not all(required):
            raise RuntimeError("Amazon SP-API credentials are not configured")
        response = await self.client.post(
            "https://api.amazon.com/auth/o2/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.settings.amazon_refresh_token,
                "client_id": self.settings.amazon_lwa_client_id,
                "client_secret": self.settings.amazon_lwa_client_secret,
            },
        )
        response.raise_for_status()
        body = response.json()
        self._token = body["access_token"]
        self._token_expires_at = time.monotonic() + int(body.get("expires_in", 3600))
        return self._token

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = await self._access_token()
        headers = {
            "x-amz-access-token": token,
            "x-amz-date": datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
            "user-agent": "AmazonMarketplaceSyncHub/0.2 (Language=Python/3.12)",
            "accept": "application/json",
        }
        url = f"{self.settings.amazon_sp_api_endpoint.rstrip('/')}{path}"
        response = await self.client.request(
            method, url, params=params, json=json, headers=headers
        )
        if response.status_code == 429:
            delay = max(
                1.0,
                min(float(response.headers.get("retry-after", "2")), 30.0),
            )
            await asyncio.sleep(delay)
            response = await self.client.request(
                method, url, params=params, json=json, headers=headers
            )
        response.raise_for_status()
        return response.json()

    async def check_connection(self, asin: str | None = None) -> dict[str, Any]:
        if not self.settings.api_live_enabled or self.settings.app_mode == "demo":
            return {"status": "demo", "catalog_verified": False}
        await self._access_token()
        result: dict[str, Any] = {"status": "ok", "lwa_verified": True}
        if asin:
            product = await self.fetch_product(asin)
            result.update(
                {
                    "catalog_verified": True,
                    "asin": product.asin,
                    "available": product.available,
                    "currency": product.currency,
                }
            )
        else:
            result["catalog_verified"] = False
        return result

    async def fetch_product(self, asin: str) -> ProductRecord:
        asin = asin.strip().upper()
        if not self.settings.api_live_enabled or self.settings.app_mode == "demo":
            return self._demo_product(asin)
        await self.catalog_limiter.wait()
        catalog = await self._request(
            "GET",
            f"/catalog/2022-04-01/items/{asin}",
            params={
                "marketplaceIds": self.settings.amazon_marketplace_id,
                "includedData": (
                    "attributes,classifications,dimensions,identifiers,images,"
                    "productTypes,relationships,salesRanks,summaries"
                ),
                "locale": "ja_JP",
            },
        )
        await self.pricing_limiter.wait()
        pricing = await self._request(
            "POST",
            "/batches/products/pricing/2022-05-01/items/competitiveSummary",
            json={
                "requests": [
                    {
                        "asin": asin,
                        "marketplaceId": self.settings.amazon_marketplace_id,
                        "includedData": [
                            "featuredBuyingOptions",
                            "referencePrices",
                            "lowestPricedOffers",
                        ],
                        "method": "GET",
                        "uri": (
                            f"/products/pricing/2022-05-01/items/{asin}/competitiveSummary"
                        ),
                    }
                ]
            },
        )
        await self.offers_limiter.wait()
        offers = await self._request(
            "GET",
            f"/products/pricing/v0/items/{asin}/offers",
            params={
                "MarketplaceId": self.settings.amazon_marketplace_id,
                "ItemCondition": "New",
                "CustomerType": "Consumer",
            },
        )
        return self._normalize(asin, catalog, pricing, offers)

    def _normalize(
        self,
        asin: str,
        catalog: dict[str, Any],
        pricing: dict[str, Any],
        offers: dict[str, Any],
    ) -> ProductRecord:
        summaries = catalog.get("summaries") or []
        summary = summaries[0] if summaries else {}
        images = [
            image["link"]
            for group in catalog.get("images") or []
            for image in group.get("images", [])
            if image.get("link")
        ]
        prices = self._extract_offer_prices(pricing) + self._extract_offer_prices(offers)
        positive = [price for price in prices if price[0] > 0]
        return ProductRecord(
            asin=asin,
            title=summary.get("itemName") or f"Amazon item {asin}",
            brand=summary.get("brand"),
            price=min((price[0] for price in positive), default=None),
            currency=next((price[1] for price in positive if price[1]), "JPY"),
            available=bool(positive),
            images=list(dict.fromkeys(images)),
            identifiers=catalog.get("identifiers") or [],
            dimensions=catalog.get("dimensions") or [],
            categories=catalog.get("classifications") or [],
            sales_ranks=catalog.get("salesRanks") or [],
            relationships=catalog.get("relationships") or [],
            attributes=catalog.get("attributes") or {},
            summaries=summaries,
            raw_catalog=catalog,
            raw_pricing=pricing,
            raw_offers=offers,
        )

    @staticmethod
    def _money(value: Any) -> tuple[float, str | None] | None:
        """Parse only a documented SP-API money object.

        Offer payloads also contain shipping, points, promotions, and reference
        amounts, so recursively accepting every ``amount`` field is unsafe.
        """
        if not isinstance(value, dict):
            return None
        amount = value.get("amount", value.get("Amount"))
        currency = value.get("currencyCode", value.get("CurrencyCode"))
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            return None
        return float(amount), str(currency) if currency else None

    def _extract_offer_prices(self, value: Any) -> list[tuple[float, str | None]]:
        """Return landed prices from actual offer-shaped objects only.

        Catalog/reference values and nested point or promotion amounts are not
        sellable offers. When no landed price is supplied, listing price plus
        the cheapest compatible shipping option is used.
        """
        found: list[tuple[float, str | None]] = []
        if isinstance(value, dict):
            landed = self._money(value.get("LandedPrice")) or self._money(
                value.get("landedPrice")
            )
            if landed and landed[0] > 0:
                found.append(landed)
            else:
                listing = self._money(value.get("ListingPrice")) or self._money(
                    value.get("listingPrice")
                )
                if listing and listing[0] > 0:
                    shipping_prices: list[tuple[float, str | None]] = []
                    direct_shipping = self._money(value.get("Shipping")) or self._money(
                        value.get("shipping")
                    )
                    if direct_shipping and direct_shipping[0] >= 0:
                        shipping_prices.append(direct_shipping)
                    options = value.get("shippingOptions", value.get("ShippingOptions"))
                    if isinstance(options, list):
                        for option in options:
                            if not isinstance(option, dict):
                                continue
                            shipping = self._money(option.get("price")) or self._money(
                                option.get("Price")
                            )
                            if shipping and shipping[0] >= 0:
                                shipping_prices.append(shipping)

                    compatible_shipping = [
                        shipping
                        for shipping in shipping_prices
                        if not listing[1]
                        or not shipping[1]
                        or listing[1].upper() == shipping[1].upper()
                    ]
                    shipping_amount = min(
                        (shipping[0] for shipping in compatible_shipping), default=0.0
                    )
                    currency = listing[1] or next(
                        (shipping[1] for shipping in compatible_shipping if shipping[1]),
                        None,
                    )
                    found.append((listing[0] + shipping_amount, currency))

            consumed = {
                "LandedPrice",
                "landedPrice",
                "ListingPrice",
                "listingPrice",
                "Shipping",
                "shipping",
                "shippingOptions",
                "ShippingOptions",
            }
            for key, child in value.items():
                if key not in consumed:
                    found.extend(self._extract_offer_prices(child))
        elif isinstance(value, list):
            for child in value:
                found.extend(self._extract_offer_prices(child))
        return found

    def _demo_product(self, asin: str) -> ProductRecord:
        return ProductRecord(
            asin=asin,
            title=f"デモ商品 {asin}",
            brand="Demo Brand",
            price=3980,
            currency="JPY",
            available=True,
            images=["https://placehold.co/800x800/png?text=Demo+Product"],
            identifiers=[
                {
                    "marketplaceId": self.settings.amazon_marketplace_id,
                    "identifiers": [
                        {"identifierType": "ASIN", "identifier": asin}
                    ],
                }
            ],
            dimensions=[
                {
                    "marketplaceId": self.settings.amazon_marketplace_id,
                    "package": {
                        "height": {"value": 10, "unit": "centimeters"},
                        "width": {"value": 20, "unit": "centimeters"},
                        "length": {"value": 30, "unit": "centimeters"},
                        "weight": {"value": 0.8, "unit": "kilograms"},
                    },
                }
            ],
            categories=[{"displayName": "Demo Category", "classificationId": "demo"}],
            attributes={"demo": [{"value": "API credentials are not configured"}]},
            raw_catalog={"mode": "demo"},
            raw_pricing={"mode": "demo"},
            raw_offers={"mode": "demo"},
            source="demo",
        )
