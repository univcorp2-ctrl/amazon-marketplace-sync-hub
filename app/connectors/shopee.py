from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any

import httpx

from app.config import Settings


class ShopeeClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.client = client or httpx.AsyncClient(timeout=30)

    async def close(self) -> None:
        await self.client.aclose()

    def _signature(self, path: str, timestamp: int) -> str:
        base = f"{self.settings.shopee_partner_id}{path}{timestamp}{self.settings.shopee_access_token}{self.settings.shopee_shop_id}"
        return hmac.new(self.settings.shopee_partner_key.encode(), base.encode(), hashlib.sha256).hexdigest()

    async def _post(self, path: str, payload: dict[str, Any], *, files: list[tuple[str, tuple[str, bytes, str]]] | None = None) -> dict[str, Any]:
        timestamp = int(time.time())
        params = {"partner_id": self.settings.shopee_partner_id, "timestamp": timestamp, "sign": self._signature(path, timestamp), "shop_id": self.settings.shopee_shop_id, "access_token": self.settings.shopee_access_token}
        url = f"{self.settings.shopee_base_url.rstrip('/')}{path}"
        response = await self.client.post(url, params=params, data=payload, files=files) if files else await self.client.post(url, params=params, json=payload)
        response.raise_for_status()
        body = response.json()
        if body.get("error"):
            raise RuntimeError(f"Shopee API error: {body.get('error')} {body.get('message', '')}")
        return body

    async def upload_images(self, image_urls: list[str]) -> list[str]:
        image_ids = []
        for index, image_url in enumerate(image_urls[:8]):
            image_response = await self.client.get(image_url)
            image_response.raise_for_status()
            body = await self._post("/api/v2/media_space/upload_image", {}, files=[("image", (f"image-{index}.jpg", image_response.content, image_response.headers.get("content-type", "image/jpeg")))])
            response = body.get("response") or {}
            image_id = response.get("image_info", {}).get("image_id") or response.get("image_id")
            if image_id:
                image_ids.append(str(image_id))
        return image_ids

    async def list_product(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.api_live_enabled or self.settings.app_mode == "demo":
            return {"response": {"item_id": f"demo-shopee-{payload['item_sku']}"}, "demo": True}
        if not all([self.settings.shopee_partner_id, self.settings.shopee_partner_key, self.settings.shopee_shop_id, self.settings.shopee_access_token]):
            raise RuntimeError("Shopee credentials are not configured")
        payload["image"] = {"image_id_list": await self.upload_images(payload.pop("image_urls", []))}
        return await self._post("/api/v2/product/add_item", payload)

    async def update_price(self, item_id: int | str, price: int) -> dict[str, Any]:
        if not self.settings.api_live_enabled or self.settings.app_mode == "demo":
            return {"demo": True, "item_id": item_id, "price": price}
        return await self._post("/api/v2/product/update_price", {"item_id": int(item_id), "price_list": [{"model_id": 0, "original_price": price}]})

    async def update_stock(self, item_id: int | str, stock: int) -> dict[str, Any]:
        if not self.settings.api_live_enabled or self.settings.app_mode == "demo":
            return {"demo": True, "item_id": item_id, "stock": stock}
        return await self._post("/api/v2/product/update_stock", {"item_id": int(item_id), "stock_list": [{"model_id": 0, "seller_stock": [{"stock": stock}]}]})
