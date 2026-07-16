from __future__ import annotations

from typing import Any
from xml.etree import ElementTree

import httpx

from app.config import Settings


class Qoo10Client:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.client = client or httpx.AsyncClient(timeout=30)

    async def close(self) -> None:
        await self.client.aclose()

    def _xml_value(self, xml_text: str, local_name: str) -> str | None:
        root = ElementTree.fromstring(xml_text)
        for element in root.iter():
            if element.tag.split("}")[-1] == local_name and element.text:
                return element.text.strip()
        return None

    async def _seller_key(self) -> str:
        response = await self.client.post(
            f"{self.settings.qoo10_base_url.rstrip('/')}/GMKT.INC.Front.OpenApiService/Certification.api/CreateCertificationKey",
            data={
                "key": self.settings.qoo10_api_key,
                "user_id": self.settings.qoo10_user_id,
                "pwd": self.settings.qoo10_password,
            },
        )
        response.raise_for_status()
        key = self._xml_value(response.text, "ResultObject")
        if not key:
            raise RuntimeError(f"Qoo10 authorization key was not returned: {response.text[:500]}")
        return key

    async def list_product(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.api_live_enabled or self.settings.app_mode == "demo":
            return {"external_id": f"demo-qoo10-{payload['SellerCode']}", "demo": True}
        required = [
            self.settings.qoo10_api_key,
            self.settings.qoo10_user_id,
            self.settings.qoo10_password,
        ]
        if not all(required):
            raise RuntimeError("Qoo10 credentials are not configured")
        seller_key = await self._seller_key()
        response = await self.client.post(
            f"{self.settings.qoo10_base_url.rstrip('/')}/GMKT.INC.Front.OpenApiService/GoodsBasicService.api/SetNewGoods",
            data={"key": seller_key, **payload},
        )
        response.raise_for_status()
        result_code = self._xml_value(response.text, "ResultCode")
        external_id = self._xml_value(response.text, "GdNo") or self._xml_value(
            response.text, "ResultObject"
        )
        if result_code not in (None, "0"):
            raise RuntimeError(f"Qoo10 SetNewGoods failed: {response.text[:1000]}")
        return {"external_id": external_id, "raw_xml": response.text}

    async def update_price_stock(self, seller_sku: str, price: int, stock: int) -> dict[str, Any]:
        if not self.settings.api_live_enabled or self.settings.app_mode == "demo":
            return {"demo": True, "seller_sku": seller_sku, "price": price, "stock": stock}
        seller_key = await self._seller_key()
        response = await self.client.post(
            f"{self.settings.qoo10_base_url.rstrip('/')}/GMKT.INC.Front.OpenApiService/GoodsOrderService.api/SetGoodsPrice",
            data={
                "key": seller_key,
                "ItemCode": "",
                "SellerCode": seller_sku,
                "ItemPrice": price,
                "ItemQty": stock,
            },
        )
        response.raise_for_status()
        result_code = self._xml_value(response.text, "ResultCode")
        if result_code not in (None, "0"):
            raise RuntimeError(f"Qoo10 SetGoodsPrice failed: {response.text[:1000]}")
        return {"raw_xml": response.text}
