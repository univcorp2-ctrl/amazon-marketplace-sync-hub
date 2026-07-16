from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import Settings, get_settings
from app.connectors.amazon import AmazonSPAPIClient
from app.connectors.qoo10 import Qoo10Client
from app.connectors.shopee import ShopeeClient
from app.db import Database
from app.models import ListingRequest
from app.services import CatalogService, MarketplaceService


class Container:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db = Database(settings.database_url)
        self.amazon = AmazonSPAPIClient(settings)
        self.shopee = ShopeeClient(settings)
        self.qoo10 = Qoo10Client(settings)
        self.catalog = CatalogService(settings, self.db, self.amazon)
        self.marketplaces = MarketplaceService(
            settings, self.db, self.catalog, self.shopee, self.qoo10
        )
        self.stop = asyncio.Event()
        self.scheduler_task: asyncio.Task[None] | None = None

    async def close(self) -> None:
        self.stop.set()
        if self.scheduler_task:
            await self.scheduler_task
        await self.amazon.close()
        await self.shopee.close()
        await self.qoo10.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    selected = settings or get_settings()
    container = Container(selected)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if selected.enable_background_sync:
            container.scheduler_task = asyncio.create_task(container.marketplaces.scheduler(container.stop))
        yield
        await container.close()

    app = FastAPI(title=selected.app_name, version="0.1.0", lifespan=lifespan)
    app.state.container = container
    app.add_middleware(
        CORSMiddleware,
        allow_origins=selected.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "mode": selected.app_mode,
            "live_api_enabled": selected.api_live_enabled,
            "amazon_source": "SP-API",
            "exact_amazon_stock_quantity": False,
        }

    @app.post("/api/products/{asin}/fetch")
    async def fetch_product(asin: str, force: bool = Query(default=False)) -> dict[str, Any]:
        try:
            return (await container.catalog.fetch(asin, force=force)).model_dump()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/products")
    async def products() -> list[dict[str, Any]]:
        return [item.model_dump() for item in container.db.list_products()]

    @app.post("/api/listings")
    async def create_listing(request: ListingRequest) -> dict[str, Any]:
        try:
            return {"results": await container.marketplaces.create_listings(request)}
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/listings")
    async def listings() -> list[dict[str, Any]]:
        return container.db.list_listings()

    @app.post("/api/sync/run")
    async def sync_run() -> dict[str, Any]:
        return await container.marketplaces.sync_all()

    static_index = Path(__file__).parent / "static" / "index.html"

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(static_index)

    return app


app = create_app()
