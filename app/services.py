from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from html import escape
from typing import Any

from app.config import Settings
from app.connectors.amazon import AmazonSPAPIClient
from app.connectors.qoo10 import Qoo10Client
from app.connectors.shopee import ShopeeClient
from app.db import Database
from app.models import (
    BulkListingRequest,
    ListingRequest,
    PriceRule,
    ProductRecord,
    calculate_target_price,
)
from app.policy import ShopeeProductPolicy


class DuplicateListingError(RuntimeError):
    pass


class CatalogService:
    def __init__(
        self, settings: Settings, db: Database, amazon: AmazonSPAPIClient
    ) -> None:
        self.settings = settings
        self.db = db
        self.amazon = amazon

    async def fetch(self, asin: str, force: bool = False) -> ProductRecord:
        normalized = asin.strip().upper()
        cached = self.db.get_product(normalized)
        if cached and not force:
            fetched = datetime.fromisoformat(cached.fetched_at)
            age = (datetime.now(UTC) - fetched).total_seconds()
            if age < self.settings.amazon_cache_ttl_seconds:
                return cached
        product = await self.amazon.fetch_product(normalized)
        self.db.upsert_product(product)
        return product

    async def search(self, query: str, max_items: int) -> list[ProductRecord]:
        asins = await self.amazon.search_asins(query, max_items=max_items)
        return [await self.fetch(asin) for asin in asins]


class MarketplaceService:
    def __init__(
        self,
        settings: Settings,
        db: Database,
        catalog: CatalogService,
        shopee: ShopeeClient,
        qoo10: Qoo10Client,
    ) -> None:
        self.settings = settings
        self.db = db
        self.catalog = catalog
        self.shopee = shopee
        self.qoo10 = qoo10
        self.policy = ShopeeProductPolicy(settings.shopee_blacklist_path, strict=settings.shopee_policy_strict)

    def _price_stock(
        self,
        product: ProductRecord,
        *,
        price_override: int | None,
        stock_override: int | None,
    ) -> tuple[int, int]:
        if price_override is not None:
            price = price_override
        else:
            if (
                self.settings.is_production
                and product.currency.upper() != self.settings.target_currency.upper()
                and self.settings.source_to_target_fx_rate == 1.0
            ):
                raise ValueError(
                    "SOURCE_TO_TARGET_FX_RATE must be configured when source and target currencies differ"
                )
            price = calculate_target_price(
                product.price,
                PriceRule(
                    markup=self.settings.price_markup,
                    fixed_fee=self.settings.price_fixed_fee,
                    minimum_margin=self.settings.minimum_margin,
                    fx_rate=self.settings.source_to_target_fx_rate,
                    marketplace_fee_rate=self.settings.marketplace_fee_rate,
                    shipping_cost=self.settings.shipping_cost,
                    rounding_step=self.settings.price_rounding_step,
                ),
            )
        stock = (
            stock_override
            if stock_override is not None
            else self.settings.stock_buffer_quantity if product.available else 0
        )
        return price, stock

    def _content_for_listing(
        self, request: ListingRequest, product: ProductRecord
    ) -> tuple[str, str, list[str]]:
        if self.settings.is_production and not self.settings.allow_source_content_reuse:
            missing = [
                name
                for name, value in (
                    ("title", request.title),
                    ("description", request.description),
                    ("image_urls", request.image_urls),
                )
                if not value
            ]
            if missing:
                raise ValueError(
                    "Production listings require seller-owned content: "
                    + ", ".join(missing)
                )

        title = request.title or product.title
        description = request.description or (
            f"{escape(title)}\n\nSource identifier: ASIN {product.asin}. "
            "The seller confirms authorization to use this content."
        )
        image_urls = request.image_urls or product.images
        if not image_urls:
            raise ValueError("At least one authorized image URL is required")
        return title, description, image_urls

    def _validate_channels(self, request: ListingRequest) -> None:
        if not request.channels:
            raise ValueError("At least one channel is required")
        disabled = sorted(set(request.channels) - set(self.settings.enabled_channels))
        if disabled:
            raise PermissionError(
                f"Channels are disabled by ENABLED_CHANNELS: {', '.join(disabled)}"
            )
        if self.settings.rights_confirmation_required and not request.rights_confirmed:
            raise PermissionError(
                "Listing is blocked until rights to the title, description, and images are confirmed."
            )

    async def create_listings(self, request: ListingRequest) -> list[dict[str, Any]]:
        self._validate_channels(request)
        if self.settings.is_production:
            configuration_issues = self.settings.production_configuration_issues(
                include_api_token=False
            )
            if configuration_issues:
                raise RuntimeError(
                    "Missing production configuration: "
                    + ", ".join(configuration_issues)
                )

        for channel in request.channels:
            issues = self.settings.listing_configuration_issues(channel)
            if channel == "shopee" and request.shopee_category_id:
                issues = [issue for issue in issues if "category_id" not in issue]
            if channel == "qoo10" and request.qoo10_category_id:
                issues = [issue for issue in issues if "category_id" not in issue]
            if channel == "qoo10" and request.shipping_no:
                issues = [issue for issue in issues if "shipping_no" not in issue]
            if issues and self.settings.is_production:
                raise ValueError("Missing listing configuration: " + ", ".join(issues))

        product = await self.catalog.fetch(request.asin)
        title, description, image_urls = self._content_for_listing(request, product)
        price, stock = self._price_stock(
            product,
            price_override=request.price_override,
            stock_override=request.stock_override,
        )
        sku = request.seller_sku or f"AMZ-{product.asin}"

        conflicts = self.db.reserve_listings(
            asin=product.asin,
            channels=request.channels,
            seller_sku=sku,
            force=request.force_relist,
        )
        if conflicts:
            raise DuplicateListingError(
                f"Listing already exists for SKU {sku}: {', '.join(conflicts)}"
            )

        policy = {
            "price_override": request.price_override,
            "stock_override": request.stock_override,
            "source_currency": product.currency,
            "target_currency": self.settings.target_currency,
            "fx_rate": self.settings.source_to_target_fx_rate,
        }
        results: list[dict[str, Any]] = []

        if "shopee" in request.channels:
            if self.settings.is_production or self.settings.shopee_market:
                decision = self.policy.evaluate(product, self.settings.shopee_market)
                if not decision.allowed:
                    raise PermissionError("Shopee policy blocked this product: " + ", ".join(decision.reasons))
            category_id = (
                request.shopee_category_id or self.settings.shopee_default_category_id
            )
            if not category_id:
                raise ValueError("Shopee category_id is required")
            payload: dict[str, Any] = {
                "item_name": title[:120],
                "description": description,
                "item_sku": sku,
                "category_id": category_id,
                "original_price": price,
                "normal_stock": stock,
                "logistic_info": self.settings.shopee_logistic_info,
                "condition": "NEW",
                "item_status": "NORMAL",
                "pre_order": {
                    "is_pre_order": request.preorder_days > 2,
                    "days_to_ship": request.preorder_days,
                },
                "weight": request.package_weight_kg
                or self.settings.default_package_weight_kg,
                "dimension": {
                    "package_length": request.package_length_cm
                    or self.settings.default_package_length_cm,
                    "package_width": request.package_width_cm
                    or self.settings.default_package_width_cm,
                    "package_height": request.package_height_cm
                    or self.settings.default_package_height_cm,
                },
                "image_urls": image_urls,
            }
            if request.shopee_attributes:
                payload["attribute_list"] = request.shopee_attributes
            try:
                response = await self.shopee.list_product(payload.copy())
                external_id = str(
                    (response.get("response") or {}).get("item_id") or ""
                ) or None
                if not external_id:
                    raise RuntimeError("Shopee add_item returned no item_id")
                self.db.upsert_listing(
                    asin=product.asin,
                    channel="shopee",
                    seller_sku=sku,
                    external_id=external_id,
                    status="listed",
                    target_price=price,
                    target_stock=stock,
                    payload={"request": payload, "response": response, "policy": policy},
                )
                results.append(
                    {
                        "channel": "shopee",
                        "external_id": external_id,
                        "response": response,
                    }
                )
            except Exception as exc:
                self.db.upsert_listing(
                    asin=product.asin,
                    channel="shopee",
                    seller_sku=sku,
                    external_id=None,
                    status="error",
                    target_price=price,
                    target_stock=stock,
                    payload={"request": payload, "error": str(exc), "policy": policy},
                )
                raise

        if "qoo10" in request.channels:
            category_id = request.qoo10_category_id or self.settings.qoo10_default_category_id
            shipping_no = request.shipping_no or self.settings.qoo10_shipping_no
            if not category_id or not shipping_no:
                raise ValueError("Qoo10 category_id and shipping_no are required")
            payload = {
                "SecondSubCat": category_id,
                "ManufactureNo": "",
                "BrandNo": "",
                "ItemTitle": title[:100],
                "SellerCode": sku,
                "IndustrialCode": "",
                "ProductionPlace": self.settings.qoo10_production_place,
                "AudultYN": "N",
                "ContactTel": self.settings.qoo10_contact_tel,
                "StandardImage": image_urls[0],
                "ItemDescription": description,
                "AdditionalOption": "",
                "ItemType": "NEW",
                "RetailPrice": price,
                "ItemPrice": price,
                "ItemQty": stock,
                "ExpireDate": "2030-12-31",
                "ShippingNo": shipping_no,
                "AvailableDateType": "0",
                "AvailableDateValue": "3",
            }
            try:
                response = await self.qoo10.list_product(payload)
                external_id = response.get("external_id")
                self.db.upsert_listing(
                    asin=product.asin,
                    channel="qoo10",
                    seller_sku=sku,
                    external_id=str(external_id) if external_id else None,
                    status="listed",
                    target_price=price,
                    target_stock=stock,
                    payload={"request": payload, "response": response, "policy": policy},
                )
                results.append(
                    {
                        "channel": "qoo10",
                        "external_id": external_id,
                        "response": response,
                    }
                )
            except Exception as exc:
                self.db.upsert_listing(
                    asin=product.asin,
                    channel="qoo10",
                    seller_sku=sku,
                    external_id=None,
                    status="error",
                    target_price=price,
                    target_stock=stock,
                    payload={"request": payload, "error": str(exc), "policy": policy},
                )
                raise
        return results

    async def bulk_shopee(self, request: BulkListingRequest) -> dict[str, Any]:
        cap = min(request.max_items, self.settings.bulk_listing_per_run_cap)
        products = await self.catalog.search(request.query, cap)
        rule = PriceRule(
            markup=(1 + request.markup_percent / 100) if request.markup_percent is not None else self.settings.price_markup,
            fixed_fee=request.fixed_profit if request.fixed_profit is not None else self.settings.price_fixed_fee,
            minimum_margin=request.minimum_margin if request.minimum_margin is not None else self.settings.minimum_margin,
            fx_rate=self.settings.source_to_target_fx_rate,
            marketplace_fee_rate=self.settings.marketplace_fee_rate,
            shipping_cost=self.settings.shipping_cost,
            rounding_step=self.settings.price_rounding_step,
        )
        existing = {str(x["asin"]).upper() for x in self.db.list_listings() if x["channel"] == "shopee"}
        candidates = []
        eligible = []
        for product in products:
            decision = self.policy.evaluate(product, self.settings.shopee_market) if self.settings.shopee_market else None
            reasons = list(decision.reasons if decision else [])
            if product.asin in existing:
                reasons.append("already_listed")
            if not product.available:
                reasons.append("amazon_offer_unavailable")
            if not product.price:
                reasons.append("missing_price")
            allowed = (decision.allowed if decision else not self.settings.is_production) and not reasons
            target_price = calculate_target_price(product.price, rule) if product.price else None
            candidates.append({"asin": product.asin, "title": product.title, "source_price": product.price, "target_price": target_price, "allowed": allowed, "policy_level": decision.level if decision else "demo", "reasons": sorted(set(reasons)), "matched_terms": decision.matched_terms if decision else []})
            if allowed:
                eligible.append((product, target_price))
        if not request.execute:
            return {"mode": "preview", "query": request.query, "market": self.settings.shopee_market or None, "candidates": candidates, "would_list": len(eligible)}
        if not self.settings.bulk_listing_enabled:
            raise PermissionError("Bulk listing is disabled")
        if self.settings.rights_confirmation_required and not request.rights_confirmed:
            raise PermissionError("Bulk listing requires rights_confirmed=true")
        if self.settings.is_production and not self.settings.shopee_market:
            raise PermissionError("SHOPEE_MARKET must be configured")
        listed = []
        errors = []
        for idx, (product, target_price) in enumerate(eligible):
            try:
                result = await self.create_listings(ListingRequest(asin=product.asin, channels=["shopee"], rights_confirmed=request.rights_confirmed, shopee_category_id=request.shopee_category_id, price_override=target_price))
                listed.extend(result)
            except Exception as exc:
                errors.append({"asin": product.asin, "error": str(exc)})
                if len(errors) >= self.settings.bulk_listing_stop_after_errors:
                    break
            if idx + 1 < len(eligible):
                await asyncio.sleep(self.settings.bulk_listing_delay_seconds)
        return {"mode": "execute", "query": request.query, "market": self.settings.shopee_market or None, "screened": candidates, "listed": listed, "errors": errors}

    async def sync_all(self) -> dict[str, Any]:
        if self.settings.is_production:
            configuration_issues = self.settings.production_configuration_issues(
                include_api_token=False
            )
            if configuration_issues:
                raise RuntimeError(
                    "Missing production configuration: "
                    + ", ".join(configuration_issues)
                )
        run_id = self.db.start_sync()
        results: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        skipped: list[dict[str, str]] = []
        for listing in self.db.list_listings():
            if listing["status"] in {"creating", "error"}:
                skipped.append(
                    {
                        "seller_sku": listing["seller_sku"],
                        "reason": f"status={listing['status']}",
                    }
                )
                continue
            try:
                product = await self.catalog.fetch(listing["asin"], force=True)
                policy = listing["payload"].get("policy") or {}
                price, stock = self._price_stock(
                    product,
                    price_override=policy.get("price_override"),
                    stock_override=policy.get("stock_override"),
                )
                if listing["channel"] == "shopee":
                    if self.settings.shopee_market:
                        decision = self.policy.evaluate(product, self.settings.shopee_market)
                        if not decision.allowed:
                            stock = 0
                    if not listing.get("external_id"):
                        raise RuntimeError("Shopee listing has no external item_id")
                    await self.shopee.update_price(listing["external_id"], price)
                    await self.shopee.update_stock(listing["external_id"], stock)
                elif listing["channel"] == "qoo10":
                    await self.qoo10.update_price_stock(
                        listing["seller_sku"], price, stock
                    )
                self.db.upsert_listing(
                    asin=listing["asin"],
                    channel=listing["channel"],
                    seller_sku=listing["seller_sku"],
                    external_id=listing.get("external_id"),
                    status="synced",
                    target_price=price,
                    target_stock=stock,
                    payload=listing["payload"],
                )
                results.append(
                    {
                        "channel": listing["channel"],
                        "seller_sku": listing["seller_sku"],
                        "price": price,
                        "stock": stock,
                    }
                )
            except Exception as exc:  # noqa: BLE001 - continue per listing
                errors.append(
                    {"seller_sku": listing["seller_sku"], "error": str(exc)}
                )
        detail = {"updated": results, "errors": errors, "skipped": skipped}
        self.db.finish_sync(run_id, "partial" if errors else "success", detail)
        return detail

    async def scheduler(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await self.sync_all()
            except Exception:  # noqa: BLE001 - next cycle must remain alive
                pass
            try:
                await asyncio.wait_for(
                    stop.wait(), timeout=self.settings.sync_interval_seconds
                )
            except TimeoutError:
                continue
