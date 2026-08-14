from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import Settings


class ShopeeClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.client = client or httpx.AsyncClient(timeout=30)
        self._access_token = settings.shopee_access_token
        self._refresh_token = settings.shopee_refresh_token
        self._access_token_expires_at = 0.0
        self._token_refresh_lock = asyncio.Lock()
        self._load_token_state()

    async def close(self) -> None:
        await self.client.aclose()

    def _signature(
        self,
        path: str,
        timestamp: int,
        *,
        access_token: str | None = None,
        shop_id: int | None = None,
    ) -> str:
        base = f"{self.settings.shopee_partner_id}{path}{timestamp}"
        if access_token is not None and shop_id is not None:
            base += f"{access_token}{shop_id}"
        return hmac.new(
            self.settings.shopee_partner_key.encode(),
            base.encode(),
            hashlib.sha256,
        ).hexdigest()

    def _token_state_path(self) -> Path | None:
        value = self.settings.shopee_token_state_file.strip()
        return Path(value) if value else None

    def _load_token_state(self) -> None:
        path = self._token_state_path()
        if path is None or not path.exists():
            return
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self._access_token = str(state.get("access_token") or self._access_token)
        self._refresh_token = str(state.get("refresh_token") or self._refresh_token)
        self._access_token_expires_at = float(state.get("expires_at") or 0)

    def _save_token_state(self) -> None:
        path = self._token_state_path()
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "access_token": self._access_token,
                    "refresh_token": self._refresh_token,
                    "expires_at": self._access_token_expires_at,
                },
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        temporary.replace(path)

    async def _refresh_access_token(
        self, *, stale_access_token: str | None = None
    ) -> None:
        """Refresh once even when concurrent requests observe an expired token.

        Shopee rotates refresh tokens. The stale-token comparison prevents a
        second request from consuming the newly rotated token after another
        request has already refreshed it.
        """
        async with self._token_refresh_lock:
            if (
                stale_access_token is not None
                and self._access_token
                and self._access_token != stale_access_token
            ):
                return
            if (
                stale_access_token is None
                and self._access_token
                and (
                    not self._access_token_expires_at
                    or time.time() < self._access_token_expires_at - 60
                )
            ):
                return
            if not all(
                [
                    self.settings.shopee_partner_id,
                    self.settings.shopee_partner_key,
                    self.settings.shopee_shop_id,
                    self._refresh_token,
                ]
            ):
                raise RuntimeError("Shopee refresh token credentials are not configured")

            path = "/api/v2/auth/access_token/get"
            timestamp = int(time.time())
            params = {
                "partner_id": self.settings.shopee_partner_id,
                "timestamp": timestamp,
                "sign": self._signature(path, timestamp),
            }
            payload = {
                "partner_id": self.settings.shopee_partner_id,
                "shop_id": self.settings.shopee_shop_id,
                "refresh_token": self._refresh_token,
            }
            response = await self.client.post(
                f"{self.settings.shopee_base_url.rstrip('/')}{path}",
                params=params,
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
            if body.get("error"):
                raise RuntimeError(
                    f"Shopee token refresh failed: {body.get('error')} {body.get('message', '')}"
                )
            token_body = body.get("response") or body
            access_token = str(token_body.get("access_token") or "")
            if not access_token:
                raise RuntimeError("Shopee token refresh returned no access_token")
            self._access_token = access_token
            self._refresh_token = str(
                token_body.get("refresh_token") or self._refresh_token
            )
            expires_in = int(
                token_body.get("expire_in")
                or token_body.get("expires_in")
                or 14400
            )
            self._access_token_expires_at = time.time() + expires_in
            self._save_token_state()

    async def _ensure_access_token(self) -> str:
        if (
            self._access_token
            and (
                not self._access_token_expires_at
                or time.time() < self._access_token_expires_at - 60
            )
        ):
            return self._access_token
        if self._refresh_token:
            await self._refresh_access_token()
        if not self._access_token:
            raise RuntimeError("Shopee access token is not configured")
        return self._access_token

    @staticmethod
    def _is_auth_error(body: dict[str, Any]) -> bool:
        text = f"{body.get('error', '')} {body.get('message', '')}".lower()
        return any(marker in text for marker in ("token", "auth", "permission"))

    async def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        files: list[tuple[str, tuple[str, bytes, str]]] | None = None,
        retry_auth: bool = True,
    ) -> dict[str, Any]:
        access_token = await self._ensure_access_token()
        timestamp = int(time.time())
        params: dict[str, Any] = {
            "partner_id": self.settings.shopee_partner_id,
            "timestamp": timestamp,
            "sign": self._signature(
                path,
                timestamp,
                access_token=access_token,
                shop_id=self.settings.shopee_shop_id,
            ),
            "shop_id": self.settings.shopee_shop_id,
            "access_token": access_token,
        }
        params.update(query or {})
        url = f"{self.settings.shopee_base_url.rstrip('/')}{path}"
        request_kwargs: dict[str, Any] = {"params": params}
        if files:
            request_kwargs.update({"data": payload or {}, "files": files})
        elif method.upper() != "GET":
            request_kwargs["json"] = payload or {}

        response = await self.client.request(method, url, **request_kwargs)
        response.raise_for_status()
        body = response.json()
        if body.get("error"):
            if retry_auth and self._refresh_token and self._is_auth_error(body):
                await self._refresh_access_token(stale_access_token=access_token)
                return await self._request(
                    method,
                    path,
                    payload=payload,
                    query=query,
                    files=files,
                    retry_auth=False,
                )
            raise RuntimeError(
                f"Shopee API error: {body.get('error')} {body.get('message', '')}"
            )
        return body

    async def check_connection(self) -> dict[str, Any]:
        if not self.settings.api_live_enabled or self.settings.app_mode == "demo":
            return {"status": "demo", "shop_id": self.settings.shopee_shop_id}
        body = await self._request("GET", "/api/v2/shop/get_shop_info")
        response = body.get("response") or body
        return {
            "status": "ok",
            "shop_id": self.settings.shopee_shop_id,
            "shop_name": response.get("shop_name"),
        }

    def _image_host_allowed(self, hostname: str) -> bool:
        normalized = hostname.rstrip(".").lower()
        if normalized == "localhost":
            return False
        try:
            address = ipaddress.ip_address(normalized)
        except ValueError:
            address = None
        if address and (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_multicast
        ):
            return False

        allowlist = [host.rstrip(".").lower() for host in self.settings.image_host_allowlist]
        if self.settings.is_production and not allowlist:
            return False
        return not allowlist or any(
            normalized == allowed or normalized.endswith(f".{allowed}")
            for allowed in allowlist
        )

    async def _download_image(self, image_url: str) -> tuple[bytes, str]:
        parsed = urlparse(image_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("Shopee images must use absolute HTTPS URLs")
        if not self._image_host_allowed(parsed.hostname):
            raise ValueError(f"Image host is not allowed: {parsed.hostname}")

        response = await self.client.get(image_url, follow_redirects=False)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        if not content_type.startswith("image/"):
            raise ValueError("Image URL did not return an image content type")
        declared = int(response.headers.get("content-length") or 0)
        if declared > self.settings.shopee_max_image_bytes:
            raise ValueError("Image exceeds SHOPEE_MAX_IMAGE_BYTES")
        if len(response.content) > self.settings.shopee_max_image_bytes:
            raise ValueError("Image exceeds SHOPEE_MAX_IMAGE_BYTES")
        return response.content, content_type

    async def upload_images(self, image_urls: list[str]) -> list[str]:
        image_ids: list[str] = []
        for index, image_url in enumerate(image_urls[:9]):
            content, content_type = await self._download_image(image_url)
            body = await self._request(
                "POST",
                "/api/v2/media_space/upload_image",
                payload={},
                files=[("image", (f"image-{index}.jpg", content, content_type))],
            )
            response = body.get("response") or {}
            image_id = response.get("image_info", {}).get("image_id") or response.get(
                "image_id"
            )
            if image_id:
                image_ids.append(str(image_id))
        return image_ids

    async def list_product(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.api_live_enabled or self.settings.app_mode == "demo":
            return {
                "response": {"item_id": f"demo-shopee-{payload['item_sku']}"},
                "demo": True,
            }
        if not all(
            [
                self.settings.shopee_partner_id,
                self.settings.shopee_partner_key,
                self.settings.shopee_shop_id,
            ]
        ):
            raise RuntimeError("Shopee credentials are not configured")
        request_payload = payload.copy()
        image_ids = await self.upload_images(request_payload.pop("image_urls", []))
        if not image_ids:
            raise ValueError("At least one image must be uploaded before listing")
        request_payload["image"] = {"image_id_list": image_ids}
        return await self._request(
            "POST", "/api/v2/product/add_item", payload=request_payload
        )

    async def update_price(self, item_id: int | str, price: int) -> dict[str, Any]:
        if not self.settings.api_live_enabled or self.settings.app_mode == "demo":
            return {"demo": True, "item_id": item_id, "price": price}
        return await self._request(
            "POST",
            "/api/v2/product/update_price",
            payload={
                "item_id": int(item_id),
                "price_list": [{"model_id": 0, "original_price": price}],
            },
        )

    async def update_stock(self, item_id: int | str, stock: int) -> dict[str, Any]:
        if not self.settings.api_live_enabled or self.settings.app_mode == "demo":
            return {"demo": True, "item_id": item_id, "stock": stock}
        return await self._request(
            "POST",
            "/api/v2/product/update_stock",
            payload={
                "item_id": int(item_id),
                "stock_list": [
                    {"model_id": 0, "seller_stock": [{"stock": stock}]}
                ],
            },
        )
