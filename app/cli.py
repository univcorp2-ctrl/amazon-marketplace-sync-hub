from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from app.config import get_settings
from app.main import Container
from app.models import ListingRequest


def _json_object(value: str | None) -> list[dict[str, Any]]:
    if not value:
        return []
    parsed = json.loads(value)
    if not isinstance(parsed, list) or not all(isinstance(item, dict) for item in parsed):
        raise ValueError("--shopee-attributes must be a JSON array of objects")
    return parsed


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    container = Container(settings)
    try:
        if args.command == "fetch":
            result = await container.catalog.fetch(args.asin, force=args.force)
            print(result.model_dump_json(indent=2))
            return 0
        if args.command == "list":
            request = ListingRequest(
                asin=args.asin,
                channels=args.channels,
                rights_confirmed=args.rights_confirmed,
                title=args.title,
                description=args.description,
                image_urls=args.image_url,
                seller_sku=args.seller_sku,
                shopee_category_id=args.shopee_category_id,
                shopee_attributes=_json_object(args.shopee_attributes),
                qoo10_category_id=args.qoo10_category_id,
                shipping_no=args.shipping_no,
                price_override=args.price_override,
                stock_override=args.stock_override,
                force_relist=args.force_relist,
            )
            print(
                json.dumps(
                    await container.marketplaces.create_listings(request),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        if args.command == "sync":
            if settings.is_production:
                issues = settings.production_configuration_issues(
                    include_api_token=False
                )
                if issues:
                    print(
                        json.dumps(
                            {"status": "blocked", "missing_config": issues},
                            ensure_ascii=False,
                            indent=2,
                        )
                    )
                    return 2
                if not container.db.list_listings():
                    print(
                        json.dumps(
                            {
                                "status": "blocked",
                                "error": "No persisted listings are available to synchronize",
                            },
                            ensure_ascii=False,
                            indent=2,
                        )
                    )
                    return 4
            result = await container.marketplaces.sync_all()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 3 if result["errors"] or (settings.is_production and not result["updated"]) else 0
        if args.command == "preflight":
            issues = settings.production_configuration_issues(include_api_token=False)
            result: dict[str, Any] = {
                "status": "blocked" if issues else "ready",
                "missing_config": issues,
                "checks": {},
            }
            if not issues and "amazon" in args.channels:
                result["checks"]["amazon"] = await container.amazon.check_connection(
                    args.asin
                )
            if not issues and "shopee" in args.channels:
                result["checks"]["shopee"] = await container.shopee.check_connection()
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 2 if issues else 0
        return 1
    finally:
        await container.close()


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Amazon Marketplace Sync Hub")
    sub = root.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch")
    fetch.add_argument("asin")
    fetch.add_argument("--force", action="store_true")

    listing = sub.add_parser("list")
    listing.add_argument("asin")
    listing.add_argument(
        "--channels", nargs="+", choices=["shopee", "qoo10"], required=True
    )
    listing.add_argument("--rights-confirmed", action="store_true")
    listing.add_argument("--title")
    listing.add_argument("--description")
    listing.add_argument("--image-url", action="append", default=[])
    listing.add_argument("--seller-sku")
    listing.add_argument("--shopee-category-id", type=int)
    listing.add_argument("--shopee-attributes")
    listing.add_argument("--qoo10-category-id")
    listing.add_argument("--shipping-no", type=int)
    listing.add_argument("--price-override", type=int)
    listing.add_argument("--stock-override", type=int)
    listing.add_argument("--force-relist", action="store_true")

    sub.add_parser("sync")
    preflight = sub.add_parser("preflight")
    preflight.add_argument(
        "--channels",
        nargs="+",
        choices=["amazon", "shopee"],
        default=["amazon", "shopee"],
    )
    preflight.add_argument("--asin")
    return root


def main() -> None:
    try:
        exit_code = asyncio.run(run(parser().parse_args()))
    except Exception as exc:  # noqa: BLE001 - CLI returns a concise non-secret error
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        exit_code = 1
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
