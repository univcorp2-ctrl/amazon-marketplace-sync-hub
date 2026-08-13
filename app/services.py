from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from html import escape
from typing import Any

from app.config import Settings
from app.connectors.amazon import AmazonSPAPIClient
from app.connectors.qoo10 import Qoo10Client
from app.connectors.shopee import ShopeeClient, ShopeeCircuitOpen
from app.db import Database
from app.models import BulkListingRequest, ListingRequest, PriceRule, ProductRecord, calculate_target_price
from app.policy import ShopeeProductPolicy


class CatalogService:
    def __init__(self, settings: Settings, db: Database, amazon: AmazonSPAPIClient) -> None:
        self.settings = settings
        self.db = db
        self.amazon = amazon

    async def fetch(self, asin: str, force: bool = False) -> ProductRecord:
        normalized = asin.strip().upper()
        cached = self.db.get_product(normalized)
        if cached and not force:
            fetched = datetime.fromisoformat(cached.fetched_at)
            if (datetime.now(UTC) - fetched).total_seconds() < self.settings.amazon_cache_ttl_seconds:
                return cached
        product = await self.amazon.fetch_product(normalized)
        self.db.upsert_product(product)
        return product

    async def search(self, query: str, max_items: int) -> list[ProductRecord]:
        asins = await self.amazon.search_asins(query, max_items=max_items)
        products: list[ProductRecord] = []
        for asin in asins:
            products.append(await self.fetch(asin))
        return products


class MarketplaceService:
    def __init__(self, settings: Settings, db: Database, catalog: CatalogService, shopee: ShopeeClient, qoo10: Qoo10Client) -> None:
        self.settings = settings
        self.db = db
        self.catalog = catalog
        self.shopee = shopee
        self.qoo10 = qoo10
        self.policy = ShopeeProductPolicy(settings.shopee_blacklist_path, strict=settings.shopee_policy_strict)

    def _price_stock(self, product: ProductRecord) -> tuple[int, int]:
        price = calculate_target_price(product.price, PriceRule(markup=self.settings.price_markup, fixed_fee=self.settings.price_fixed_fee, minimum_margin=self.settings.minimum_margin))
        stock = self.settings.stock_buffer_quantity if product.available else 0
        return price, stock

    def _existing_shopee_asins(self) -> set[str]:
        return {str(item["asin"]).upper() for item in self.db.list_listings() if item["channel"] == "shopee"}

    def _today_shopee_listing_count(self) -> int:
        today = datetime.now(UTC).date().isoformat()
        return sum(1 for item in self.db.list_listings() if item["channel"] == "shopee" and item["status"] in {"listed", "synced"} and str(item.get("updated_at", "")).startswith(today))

    async def create_listings(self, request: ListingRequest) -> list[dict[str, Any]]:
        if not request.channels:
            raise ValueError("At least one channel is required")
        if self.settings.rights_confirmation_required and not request.rights_confirmed:
            raise PermissionError("Listing is blocked until you confirm rights to the title, description, and images.")
        product = await self.catalog.fetch(request.asin)
        price, stock = self._price_stock(product)
        sku = request.seller_sku or f"AMZ-{product.asin}"
        title = request.title or product.title
        description = request.description or (f"{escape(title)}\n\nSource identifier: ASIN {product.asin}. The seller confirms authorization to use this content.")
        image_urls = request.image_urls or product.images
        results: list[dict[str, Any]] = []
        if "shopee" in request.channels:
            decision = self.policy.evaluate(product, self.settings.shopee_market)
            if not decision.allowed:
                raise PermissionError(f"Shopee policy blocked this product: {', '.join(decision.reasons)}")
            category_id = request.shopee_category_id or self.settings.shopee_default_category_id
            if not category_id:
                raise ValueError("Shopee category_id is required")
            payload = {"item_name": title[:120], "description": description, "item_sku": sku, "category_id": category_id, "original_price": price, "normal_stock": stock, "logistic_info": self.settings.shopee_logistic_info, "condition": "NEW", "item_status": "NORMAL", "pre_order": {"is_pre_order": False, "days_to_ship": 2}, "weight": 0.8, "dimension": {"package_length": 30, "package_width": 20, "package_height": 10}, "image_urls": image_urls}
            response = await self.shopee.list_product(payload.copy())
            external_id = str((response.get("response") or {}).get("item_id") or "") or None
            self.db.upsert_listing(asin=product.asin, channel="shopee", seller_sku=sku, external_id=external_id, status="listed", target_price=price, target_stock=stock, payload={"request": payload, "response": response})
            results.append({"channel": "shopee", "external_id": external_id, "response": response})
        if "qoo10" in request.channels:
            category_id = request.qoo10_category_id or self.settings.qoo10_default_category_id
            shipping_no = request.shipping_no or self.settings.qoo10_shipping_no
            if not category_id or not shipping_no:
                raise ValueError("Qoo10 category_id and shipping_no are required")
            payload = {"SecondSubCat": category_id, "ManufactureNo": "", "BrandNo": "", "ItemTitle": title[:100], "SellerCode": sku, "IndustrialCode": "", "ProductionPlace": self.settings.qoo10_production_place, "AudultYN": "N", "ContactTel": self.settings.qoo10_contact_tel, "StandardImage": image_urls[0] if image_urls else "", "ItemDescription": description, "AdditionalOption": "", "ItemType": "NEW", "RetailPrice": price, "ItemPrice": price, "ItemQty": stock, "ExpireDate": "2030-12-31", "ShippingNo": shipping_no, "AvailableDateType": "0", "AvailableDateValue": "3"}
            response = await self.qoo10.list_product(payload)
            external_id = response.get("external_id")
            self.db.upsert_listing(asin=product.asin, channel="qoo10", seller_sku=sku, external_id=str(external_id) if external_id else None, status="listed", target_price=price, target_stock=stock, payload={"request": payload, "response": response})
            results.append({"channel": "qoo10", "external_id": external_id, "response": response})
        return results

    async def bulk_shopee(self, request: BulkListingRequest) -> dict[str, Any]:
        cap = min(request.max_items, self.settings.bulk_listing_per_run_cap)
        products = await self.catalog.search(request.query, max_items=cap)
        existing = self._existing_shopee_asins()
        preview: list[dict[str, Any]] = []
        eligible: list[ProductRecord] = []
        for product in products:
            decision = self.policy.evaluate(product, self.settings.shopee_market)
            reasons = list(decision.reasons)
            if product.asin in existing:
                reasons.append("already_listed")
            if not product.available:
                reasons.append("amazon_offer_unavailable")
            if not product.price or product.price <= 0:
                reasons.append("missing_price")
            allowed = decision.allowed and not reasons
            preview.append({"asin": product.asin, "title": product.title, "allowed": allowed, "policy_level": decision.level, "reasons": sorted(set(reasons)), "matched_terms": decision.matched_terms})
            if allowed:
                eligible.append(product)
        if not request.execute:
            return {"mode": "preview", "query": request.query, "market": self.settings.shopee_market or None, "candidates": preview, "would_list": len(eligible)}
        if not self.settings.bulk_listing_enabled:
            raise PermissionError("Bulk listing is disabled; set BULK_LISTING_ENABLED=true only after shop validation")
        if self.settings.app_mode == "production" and not all(self.settings.live_readiness().values()):
            raise PermissionError("Production live readiness gates are not all satisfied")
        if self.settings.rights_confirmation_required and not request.rights_confirmed:
            raise PermissionError("Bulk listing requires rights_confirmed=true")
        if self.settings.shopee_market.upper() not in self.policy.supported_markets:
            raise PermissionError("A supported SHOPEE_MARKET must be explicitly configured")
        if self._today_shopee_listing_count() >= self.settings.bulk_listing_daily_cap:
            raise PermissionError("Daily Shopee listing safety cap reached")
        results: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        remaining_today = max(0, self.settings.bulk_listing_daily_cap - self._today_shopee_listing_count())
        for index, product in enumerate(eligible[:remaining_today]):
            try:
                created = await self.create_listings(ListingRequest(asin=product.asin, channels=["shopee"], rights_confirmed=request.rights_confirmed, shopee_category_id=request.shopee_category_id))
                results.extend(created)
            except ShopeeCircuitOpen:
                raise
            except Exception as exc:  # noqa: BLE001
                errors.append({"asin": product.asin, "error": str(exc)})
                if len(errors) >= self.settings.bulk_listing_stop_after_errors:
                    break
            if index + 1 < len(eligible):
                await asyncio.sleep(self.settings.bulk_listing_delay_seconds)
        return {"mode": "execute", "query": request.query, "market": self.settings.shopee_market, "screened": preview, "listed": results, "errors": errors}

    async def sync_all(self) -> dict[str, Any]:
        run_id = self.db.start_sync()
        results: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        for listing in self.db.list_listings():
            try:
                product = await self.catalog.fetch(listing["asin"], force=True)
                price, stock = self._price_stock(product)
                if listing["channel"] == "shopee" and listing.get("external_id"):
                    decision = self.policy.evaluate(product, self.settings.shopee_market)
                    if not decision.allowed:
                        await self.shopee.update_stock(listing["external_id"], 0)
                        self.db.upsert_listing(asin=listing["asin"], channel=listing["channel"], seller_sku=listing["seller_sku"], external_id=listing.get("external_id"), status="policy_blocked", target_price=price, target_stock=0, payload=listing["payload"])
                        results.append({"channel": "shopee", "seller_sku": listing["seller_sku"], "price": price, "stock": 0, "policy_blocked": decision.reasons})
                        continue
                    await self.shopee.update_price(listing["external_id"], price)
                    await self.shopee.update_stock(listing["external_id"], stock)
                elif listing["channel"] == "qoo10":
                    await self.qoo10.update_price_stock(listing["seller_sku"], price, stock)
                self.db.upsert_listing(asin=listing["asin"], channel=listing["channel"], seller_sku=listing["seller_sku"], external_id=listing.get("external_id"), status="synced", target_price=price, target_stock=stock, payload=listing["payload"])
                results.append({"channel": listing["channel"], "seller_sku": listing["seller_sku"], "price": price, "stock": stock})
            except Exception as exc:  # noqa: BLE001
                errors.append({"seller_sku": listing["seller_sku"], "error": str(exc)})
                if isinstance(exc, ShopeeCircuitOpen):
                    break
        detail = {"updated": results, "errors": errors}
        self.db.finish_sync(run_id, "partial" if errors else "success", detail)
        return detail

    async def scheduler(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await self.sync_all()
            except Exception:  # noqa: BLE001
                pass
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.settings.sync_interval_seconds)
            except TimeoutError:
                continue
