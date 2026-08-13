from __future__ import annotations

import asyncio
import json
import os
import re

from app.config import get_settings
from app.main import Container
from app.models import ListingRequest


def optional_int(name: str) -> int | None:
    value = os.getenv(name, "").strip()
    return int(value) if value else None


def optional_float(name: str) -> float | None:
    value = os.getenv(name, "").strip()
    return float(value) if value else None


def parse_images(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[\n,]+", value) if part.strip()]


async def main() -> None:
    if os.getenv("RIGHTS_CONFIRMED", "").lower() != "true":
        raise RuntimeError("rights_confirmed must be true for a live listing")

    attributes_raw = os.getenv("SHOPEE_ATTRIBUTES", "").strip()
    attributes = json.loads(attributes_raw) if attributes_raw else []
    request = ListingRequest(
        asin=os.environ["LISTING_ASIN"],
        channels=["shopee"],
        rights_confirmed=True,
        title=os.environ["LISTING_TITLE"],
        description=os.environ["LISTING_DESCRIPTION"],
        image_urls=parse_images(os.environ["LISTING_IMAGE_URLS"]),
        seller_sku=os.getenv("SELLER_SKU") or None,
        shopee_category_id=int(os.environ["SHOPEE_CATEGORY_ID"]),
        shopee_attributes=attributes,
        price_override=optional_int("PRICE_OVERRIDE"),
        stock_override=optional_int("STOCK_OVERRIDE"),
        package_weight_kg=optional_float("PACKAGE_WEIGHT_KG"),
        package_length_cm=optional_float("PACKAGE_LENGTH_CM"),
        package_width_cm=optional_float("PACKAGE_WIDTH_CM"),
        package_height_cm=optional_float("PACKAGE_HEIGHT_CM"),
        force_relist=os.getenv("FORCE_RELIST", "").lower() == "true",
    )
    container = Container(get_settings())
    try:
        result = await container.marketplaces.create_listings(request)
        print(
            json.dumps(
                {"status": "listed", "results": result},
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        await container.close()


if __name__ == "__main__":
    asyncio.run(main())
