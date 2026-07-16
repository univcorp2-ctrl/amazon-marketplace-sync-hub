from __future__ import annotations

import argparse
import asyncio
import json

from app.config import get_settings
from app.main import Container
from app.models import ListingRequest


async def run(args: argparse.Namespace) -> None:
    container = Container(get_settings())
    try:
        if args.command == "fetch":
            result = await container.catalog.fetch(args.asin, force=args.force)
            print(result.model_dump_json(indent=2))
        elif args.command == "list":
            request = ListingRequest(
                asin=args.asin,
                channels=args.channels,
                rights_confirmed=args.rights_confirmed,
                shopee_category_id=args.shopee_category_id,
                qoo10_category_id=args.qoo10_category_id,
                shipping_no=args.shipping_no,
            )
            print(json.dumps(await container.marketplaces.create_listings(request), ensure_ascii=False, indent=2))
        elif args.command == "sync":
            print(json.dumps(await container.marketplaces.sync_all(), ensure_ascii=False, indent=2))
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
    listing.add_argument("--channels", nargs="+", choices=["shopee", "qoo10"], required=True)
    listing.add_argument("--rights-confirmed", action="store_true")
    listing.add_argument("--shopee-category-id", type=int)
    listing.add_argument("--qoo10-category-id")
    listing.add_argument("--shipping-no", type=int)
    sub.add_parser("sync")
    return root


def main() -> None:
    asyncio.run(run(parser().parse_args()))


if __name__ == "__main__":
    main()
